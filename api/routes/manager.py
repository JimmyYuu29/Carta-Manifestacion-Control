"""
Manager Routes - Manager-side API endpoints for authorization and download
Rutas de Manager - Endpoints de API del lado del manager para autorizacion y descarga

SECURITY REQUIREMENTS:
1. Multi-supervisor authentication with individual passwords
2. Approval code validation (time-limited, single-use)
3. Download token is short-lived and single-use
4. Only SUBMITTED status reviews can be downloaded
5. All download operations are audited
"""

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import Optional, List
import os

from ..models.review import Review, ReviewStatus
from ..services.storage import ReviewStorage
from ..services.render_html import HtmlRenderer
from ..services.render_docx import DocxRenderService
from ..services.supervisor_auth import get_supervisor_auth_service, Supervisor


router = APIRouter(prefix="/manager", tags=["manager"])

# Initialize services
storage = ReviewStorage()
html_renderer = HtmlRenderer()
docx_service = DocxRenderService()
supervisor_auth = get_supervisor_auth_service()

# Token TTL in seconds (default 5 minutes)
TOKEN_TTL_SECONDS = int(os.environ.get("DOWNLOAD_TOKEN_TTL", "300"))


def get_client_ip(request: Request) -> str:
    """Extract client IP from request"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class SupervisorInfo(BaseModel):
    id: str
    name: str
    email: str


class SupervisorsListResponse(BaseModel):
    supervisors: List[SupervisorInfo]


class AuthorizeRequest(BaseModel):
    approval_code: str
    password: str


class AuthorizeResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    download_url: Optional[str] = None
    preview_url: Optional[str] = None
    expires_in_seconds: Optional[int] = None
    supervisor_name: Optional[str] = None
    client_name: Optional[str] = None
    error: Optional[str] = None


class ApprovalCodeRequest(BaseModel):
    review_id: str
    supervisor_id: str


class ApprovalCodeResponse(BaseModel):
    success: bool
    approval_code: Optional[str] = None
    supervisor_name: Optional[str] = None
    expires_at: Optional[str] = None
    error: Optional[str] = None


@router.get("/supervisors", response_model=SupervisorsListResponse)
async def list_supervisors():
    """
    Get list of available supervisors (for dropdown selection)
    Obtener lista de supervisores disponibles (para seleccion)
    """
    supervisors = supervisor_auth.get_supervisors_list()
    return SupervisorsListResponse(
        supervisors=[
            SupervisorInfo(id=s.id, name=s.name, email=s.email)
            for s in supervisors
        ]
    )


@router.post("/approval-code", response_model=ApprovalCodeResponse)
async def create_approval_code(req: ApprovalCodeRequest, request: Request):
    """
    Create a new approval code for a review
    Crear un nuevo codigo de aprobacion para una revision

    Employee calls this after submitting a review.
    The code is sent to the selected supervisor.
    """
    # Validate review exists
    review = storage.load(req.review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    # Check review is submitted
    if review.status != ReviewStatus.SUBMITTED:
        return ApprovalCodeResponse(
            success=False,
            error=f"Review must be SUBMITTED to generate approval code. Current status: {review.status.value}"
        )

    # Validate supervisor exists
    supervisor = supervisor_auth.get_supervisor(req.supervisor_id)
    if not supervisor:
        return ApprovalCodeResponse(
            success=False,
            error=f"Unknown supervisor: {req.supervisor_id}"
        )

    try:
        # Create approval code
        code, approval = supervisor_auth.create_approval_code(
            review_id=req.review_id,
            supervisor_id=req.supervisor_id
        )

        # Log the code generation in audit
        from ..models.review import AuditLogEntry
        from datetime import datetime

        review.add_audit_log(AuditLogEntry(
            timestamp=datetime.utcnow().isoformat(),
            action="approval_code_generated",
            actor="employee",
            ip_address=get_client_ip(request),
            details=f"Approval code generated for supervisor: {supervisor.name}"
        ))
        storage.save(review)

        return ApprovalCodeResponse(
            success=True,
            approval_code=code,
            supervisor_name=supervisor.name,
            expires_at=approval.expires_at
        )

    except Exception as e:
        return ApprovalCodeResponse(
            success=False,
            error=str(e)
        )


@router.get("/reviews/{review_id}", response_class=HTMLResponse)
async def manager_entry_page(review_id: str, request: Request):
    """
    Manager download entry page with approval code and password form
    Pagina de entrada de descarga del manager con formulario de codigo y contrasena

    Returns HTML page with approval code + password input form.
    """
    review = storage.load(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    # Render manager page
    html = html_renderer.render_manager_page(
        review_id=review_id,
        doc_type=review.doc_type,
        status=review.status.value,
        client_name=review.data_json.get("Nombre_Cliente", "")
    )

    return HTMLResponse(content=html)


@router.post("/authorize", response_model=AuthorizeResponse)
async def authorize_with_code(req: AuthorizeRequest, request: Request):
    """
    Authorize manager using approval code and supervisor password
    Autorizar al manager usando codigo de aprobacion y contrasena de supervisor

    SECURITY:
    1. Approval code must be valid (not expired, not used)
    2. Password must match the supervisor assigned to the code
    3. Returns short-lived, single-use download token
    """
    # Validate approval code
    is_valid, approval_code, error_msg = supervisor_auth.validate_approval_code(req.approval_code)
    if not is_valid:
        return AuthorizeResponse(success=False, error=error_msg)

    # Get review
    review = storage.load(approval_code.review_id)
    if not review:
        return AuthorizeResponse(success=False, error="Review not found")

    # Check review status
    if not review.can_download():
        return AuthorizeResponse(
            success=False,
            error=f"Review is {review.status.value}. Only SUBMITTED reviews can be downloaded."
        )

    # Verify supervisor password
    if not supervisor_auth.verify_password(approval_code.supervisor_id, req.password):
        # Log failed attempt
        from ..models.review import AuditLogEntry
        from datetime import datetime

        review.add_audit_log(AuditLogEntry(
            timestamp=datetime.utcnow().isoformat(),
            action="authorize_failed",
            actor=f"supervisor:{approval_code.supervisor_id}",
            ip_address=get_client_ip(request),
            details="Invalid supervisor password"
        ))
        storage.save(review)

        return AuthorizeResponse(
            success=False,
            error="Contrasena incorrecta"
        )

    # Mark approval code as used
    supervisor_auth.use_approval_code(req.approval_code)

    # Generate download token
    token = storage.create_download_token(approval_code.review_id, TOKEN_TTL_SECONDS)

    # Log successful authorization
    from ..models.review import AuditLogEntry
    from datetime import datetime

    supervisor = supervisor_auth.get_supervisor(approval_code.supervisor_id)
    review.add_audit_log(AuditLogEntry(
        timestamp=datetime.utcnow().isoformat(),
        action="authorize_success",
        actor=f"supervisor:{approval_code.supervisor_id}",
        ip_address=get_client_ip(request),
        details=f"Authorized by {supervisor.name if supervisor else 'Unknown'}. Download token issued, expires in {TOKEN_TTL_SECONDS}s"
    ))
    storage.save(review)

    base_url = str(request.base_url).rstrip("/")
    download_url = f"{base_url}/manager/reviews/{approval_code.review_id}/download?token={token.token}"
    preview_url = f"{base_url}/manager/reviews/{approval_code.review_id}/preview?token={token.token}"

    return AuthorizeResponse(
        success=True,
        token=token.token,
        download_url=download_url,
        preview_url=preview_url,
        expires_in_seconds=TOKEN_TTL_SECONDS,
        supervisor_name=supervisor.name if supervisor else None,
        client_name=review.data_json.get("Nombre_Cliente", "")
    )


@router.post("/reviews/{review_id}/authorize", response_model=AuthorizeResponse)
async def authorize_download_legacy(review_id: str, req: AuthorizeRequest, request: Request):
    """
    Legacy endpoint - redirects to new authorize flow
    Endpoint legacy - redirige al nuevo flujo de autorizacion
    """
    # For backwards compatibility, try to authorize using the new flow
    return await authorize_with_code(req, request)


@router.get("/reviews/{review_id}/preview")
async def manager_preview(review_id: str, token: str, request: Request):
    """
    Manager preview of the document before download
    Vista previa del manager antes de descargar

    SECURITY: Requires valid download token
    """
    review = storage.load(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    # Validate token (don't consume it for preview)
    stored_token = storage.get_token(token)
    if not stored_token or stored_token.review_id != review_id:
        raise HTTPException(status_code=403, detail="Invalid or expired token")

    # Build download URL
    base_url = str(request.base_url).rstrip("/")
    download_url = f"{base_url}/manager/reviews/{review_id}/download?token={token}"

    # Render document preview using template.html
    html = html_renderer.render_document_preview(
        doc_type=review.doc_type,
        data_json=review.data_json,
        review_id=review_id,
        status=review.status.value,
        can_edit=False,
        editable_fields=[],
        mode="manager",
        download_url=download_url,
        token=token
    )

    return HTMLResponse(content=html)


@router.get("/reviews/{review_id}/download")
async def download_document(review_id: str, token: str, request: Request):
    """
    Download Word document with token verification
    Descargar documento Word con verificacion de token

    SECURITY:
    1. Token must be valid and not expired
    2. Token must match review_id
    3. Token is single-use (consumed on download)
    4. Only SUBMITTED status allowed
    5. Download is audited
    """
    review = storage.load(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    # SECURITY: Check status
    if review.status not in (ReviewStatus.SUBMITTED, ReviewStatus.DOWNLOADED):
        raise HTTPException(
            status_code=403,
            detail=f"Review is {review.status.value}. Only SUBMITTED reviews can be downloaded."
        )

    # SECURITY: Validate and consume token
    if not storage.validate_and_consume_token(token, review_id):
        raise HTTPException(
            status_code=403,
            detail="Invalid or expired download token"
        )

    client_ip = get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "")

    # Render document
    try:
        doc_path, filename = docx_service.render(
            doc_type=review.doc_type,
            data_json=review.data_json,
            review_id=review_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate document: {str(e)}")

    # Mark as downloaded
    review.mark_downloaded(
        actor="supervisor",
        ip_address=client_ip,
        user_agent=user_agent
    )
    storage.save(review)

    # Return file
    return FileResponse(
        path=str(doc_path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


@router.get("/reviews/{review_id}/audit")
async def get_audit_log(review_id: str, token: str):
    """
    Get audit log for a review (requires valid token)
    Obtener log de auditoria para una revision (requiere token valido)
    """
    review = storage.load(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    # Validate token exists and matches (but don't consume for audit view)
    stored_token = storage.get_token(token)
    if not stored_token or stored_token.review_id != review_id:
        raise HTTPException(status_code=403, detail="Invalid token")

    return {
        "review_id": review_id,
        "status": review.status.value,
        "audit_log": [entry.to_dict() for entry in review.audit_log]
    }


@router.get("/reviews/{review_id}/info")
async def get_review_info(review_id: str):
    """
    Get basic review info (no sensitive data, no auth required)
    Obtener info basica de revision (sin datos sensibles, sin auth)
    """
    review = storage.load(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    return {
        "review_id": review_id,
        "doc_type": review.doc_type,
        "status": review.status.value,
        "client_name": review.data_json.get("Nombre_Cliente", ""),
        "created_at": review.created_at.isoformat(),
        "submitted_at": review.submitted_at.isoformat() if review.submitted_at else None,
        "downloaded_at": review.downloaded_at.isoformat() if review.downloaded_at else None,
        "can_download": review.can_download()
    }


@router.get("/code/{code}/info")
async def get_code_info(code: str):
    """
    Get information about an approval code
    Obtener informacion sobre un codigo de aprobacion
    """
    info = supervisor_auth.get_approval_code_info(code)
    if not info:
        raise HTTPException(status_code=404, detail="Approval code not found")

    return info
