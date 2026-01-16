"""
Review Routes - Employee-side API endpoints for review management
Rutas de Review - Endpoints de API del lado del empleado para gestion de revisiones

SECURITY REQUIREMENTS:
1. No endpoint returns or exposes Word document to employees
2. All data updates go through whitelist validation
3. SUBMITTED status blocks all further edits (403)
4. Audit log records all operations
"""

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from datetime import datetime
import os

from ..models.review import Review, ReviewStatus
from ..services.storage import ReviewStorage
from ..services.validation import SchemaValidator
from ..services.render_html import HtmlRenderer


router = APIRouter(prefix="/reviews", tags=["reviews"])

# Initialize services
storage = ReviewStorage()
validator = SchemaValidator()
html_renderer = HtmlRenderer()


# Request/Response models
class CreateReviewRequest(BaseModel):
    doc_type: str
    initial_data: Dict[str, Any]
    created_by: Optional[str] = "employee"


class CreateReviewResponse(BaseModel):
    review_id: str
    status: str
    manager_link: str


class UpdateDataRequest(BaseModel):
    data: Dict[str, Any]


class UpdateDataResponse(BaseModel):
    success: bool
    updated_fields: List[str]
    rejected_fields: List[str]
    errors: List[dict]


class ReviewDataResponse(BaseModel):
    review_id: str
    doc_type: str
    status: str
    data: Dict[str, Any]
    editable_fields: List[str]
    can_edit: bool


class SubmitResponse(BaseModel):
    success: bool
    status: str
    manager_link: str


def get_client_ip(request: Request) -> str:
    """Extract client IP from request"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def get_base_url(request: Request) -> str:
    """Get base URL from request"""
    return str(request.base_url).rstrip("/")


@router.post("", response_model=CreateReviewResponse)
async def create_review(req: CreateReviewRequest, request: Request):
    """
    Create a new review from initial data
    Crear una nueva revision desde datos iniciales

    Employee creates a review with initial form data.
    Status starts as DRAFT.
    """
    # Validate doc_type exists
    try:
        validator.load_schema(req.doc_type)
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail=f"Unknown doc_type: {req.doc_type}")

    # Create review
    review = Review.create(
        doc_type=req.doc_type,
        initial_data=req.initial_data,
        created_by=req.created_by or "employee"
    )

    # Add IP to audit log
    review.audit_log[-1].ip_address = get_client_ip(request)

    # Save
    storage.save(review)

    return CreateReviewResponse(
        review_id=review.review_id,
        status=review.status.value,
        manager_link=review.get_manager_link(get_base_url(request))
    )


@router.get("/{review_id}/preview", response_class=HTMLResponse)
async def get_preview(review_id: str, request: Request):
    """
    Get HTML preview of the review document
    Obtener previsualizacion HTML del documento de revision

    Returns rendered HTML that matches Word output.
    Editable fields are marked for UI interaction.
    SECURITY: No Word file is ever returned to this endpoint.
    """
    review = storage.load(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    # Get editable fields from schema
    editable_fields = validator.get_editable_fields(review.doc_type)

    # Render document preview using template.html
    html = html_renderer.render_document_preview(
        doc_type=review.doc_type,
        data_json=review.data_json,
        review_id=review_id,
        status=review.status.value,
        can_edit=review.can_edit(),
        editable_fields=editable_fields,
        mode="employee"
    )

    return HTMLResponse(content=html)


@router.get("/{review_id}/data", response_model=ReviewDataResponse)
async def get_data(review_id: str):
    """
    Get current review data (editable fields only shown as editable)
    Obtener datos actuales de la revision

    Returns full data but marks which fields are editable.
    """
    review = storage.load(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    editable_fields = validator.get_editable_fields(review.doc_type)

    return ReviewDataResponse(
        review_id=review.review_id,
        doc_type=review.doc_type,
        status=review.status.value,
        data=review.data_json,
        editable_fields=editable_fields,
        can_edit=review.can_edit()
    )


@router.patch("/{review_id}/data", response_model=UpdateDataResponse)
async def update_data(review_id: str, req: UpdateDataRequest, request: Request):
    """
    Update review data with whitelist enforcement
    Actualizar datos de revision con aplicacion de lista blanca

    SECURITY:
    1. Only DRAFT status allows updates (403 otherwise)
    2. Only editable fields are updated (others silently rejected + logged)
    3. All values validated against schema
    4. All operations audited
    """
    review = storage.load(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    # SECURITY: Check status
    if not review.can_edit():
        raise HTTPException(
            status_code=403,
            detail=f"Review is {review.status.value} and cannot be edited"
        )

    client_ip = get_client_ip(request)

    # SECURITY: Validate and filter through whitelist
    validation_result = validator.validate_update(review.doc_type, req.data)

    # Log unauthorized field attempts
    for field in validation_result.unauthorized_fields:
        review.log_unauthorized_attempt(
            field_name=field,
            attempted_value=req.data.get(field),
            actor=review.created_by,
            ip_address=client_ip
        )

    # Update valid fields
    updated_fields = []
    for field_name, value in validation_result.filtered_data.items():
        if review.update_field(field_name, value, review.created_by, client_ip):
            updated_fields.append(field_name)

    # Save
    storage.save(review)

    return UpdateDataResponse(
        success=validation_result.is_valid,
        updated_fields=updated_fields,
        rejected_fields=validation_result.unauthorized_fields,
        errors=[{"field": e.field, "message": e.message} for e in validation_result.errors]
    )


@router.post("/{review_id}/submit", response_model=SubmitResponse)
async def submit_review(review_id: str, request: Request):
    """
    Submit review for manager approval (freeze it)
    Enviar revision para aprobacion del manager (congelarla)

    SECURITY:
    1. Transitions status to SUBMITTED
    2. No further PATCH calls allowed after this
    3. Returns manager download link
    """
    review = storage.load(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    if not review.can_submit():
        raise HTTPException(
            status_code=409,
            detail=f"Review is already {review.status.value}"
        )

    client_ip = get_client_ip(request)

    # Submit (freeze)
    success = review.submit(review.created_by, client_ip)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to submit review")

    # Save
    storage.save(review)

    return SubmitResponse(
        success=True,
        status=review.status.value,
        manager_link=review.get_manager_link(get_base_url(request))
    )


@router.get("/{review_id}/schema")
async def get_schema(review_id: str):
    """
    Get schema for UI rendering
    Obtener schema para renderizado de UI
    """
    review = storage.load(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    return validator.get_schema_for_ui(review.doc_type)


@router.get("/{review_id}/status")
async def get_status(review_id: str, request: Request):
    """
    Get current review status
    Obtener estado actual de la revision
    """
    review = storage.load(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    return {
        "review_id": review.review_id,
        "status": review.status.value,
        "can_edit": review.can_edit(),
        "can_submit": review.can_submit(),
        "submitted_at": review.submitted_at.isoformat() if review.submitted_at else None,
        "manager_link": review.get_manager_link(get_base_url(request)) if review.status != ReviewStatus.DRAFT else None
    }
