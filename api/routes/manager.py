"""
Manager Routes - Manager-side API endpoints for authorization and download
Rutas de Manager - Endpoints de API del lado del manager para autorizacion y descarga

SECURITY REQUIREMENTS:
1. Manager password verified server-side only (from env var)
2. Download token is short-lived and single-use
3. Only SUBMITTED status reviews can be downloaded
4. All download operations are audited
5. Word file never exposed via static routes
"""

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import Optional
import os
import hashlib

from ..models.review import Review, ReviewStatus
from ..services.storage import ReviewStorage
from ..services.render_html import HtmlRenderer
from ..services.render_docx import DocxRenderService


router = APIRouter(prefix="/manager", tags=["manager"])

# Initialize services
storage = ReviewStorage()
html_renderer = HtmlRenderer()
docx_service = DocxRenderService()

# SECURITY: Manager password from environment variable only
# Never hardcode, never expose to frontend
MANAGER_PASSWORD_HASH = os.environ.get("MANAGER_PASSWORD_HASH", "")
MANAGER_PASSWORD = os.environ.get("MANAGER_PASSWORD", "")  # For development only

# Token TTL in seconds (default 5 minutes)
TOKEN_TTL_SECONDS = int(os.environ.get("DOWNLOAD_TOKEN_TTL", "300"))


def verify_manager_password(password: str) -> bool:
    """
    Verify manager password against stored hash or plain password
    SECURITY: In production, always use MANAGER_PASSWORD_HASH (SHA-256)
    """
    if MANAGER_PASSWORD_HASH:
        # Production: Compare hash
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        return password_hash == MANAGER_PASSWORD_HASH

    if MANAGER_PASSWORD:
        # Development: Direct comparison (NOT recommended for production)
        return password == MANAGER_PASSWORD

    # No password configured - reject all
    return False


def get_client_ip(request: Request) -> str:
    """Extract client IP from request"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class AuthorizeRequest(BaseModel):
    password: str


class AuthorizeResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    download_url: Optional[str] = None
    expires_in_seconds: Optional[int] = None
    error: Optional[str] = None


@router.get("/reviews/{review_id}", response_class=HTMLResponse)
async def manager_entry_page(review_id: str, request: Request):
    """
    Manager download entry page with password form
    Pagina de entrada de descarga del manager con formulario de contrasena

    Returns HTML page with password input form.
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


@router.post("/reviews/{review_id}/authorize", response_model=AuthorizeResponse)
async def authorize_download(review_id: str, req: AuthorizeRequest, request: Request):
    """
    Authorize manager for download with password verification
    Autorizar al manager para descarga con verificacion de contrasena

    SECURITY:
    1. Password verified server-side only
    2. Only SUBMITTED status allowed
    3. Returns short-lived, single-use token
    4. Token bound to review_id
    """
    review = storage.load(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    # SECURITY: Check status
    if not review.can_download():
        return AuthorizeResponse(
            success=False,
            error=f"Review is {review.status.value}. Only SUBMITTED reviews can be downloaded."
        )

    # SECURITY: Verify password
    if not verify_manager_password(req.password):
        # Log failed attempt
        from ..models.review import AuditLogEntry
        from datetime import datetime

        review.add_audit_log(AuditLogEntry(
            timestamp=datetime.utcnow().isoformat(),
            action="authorize_failed",
            actor="manager",
            ip_address=get_client_ip(request),
            details="Invalid manager password"
        ))
        storage.save(review)

        return AuthorizeResponse(
            success=False,
            error="Invalid password"
        )

    # Generate download token
    token = storage.create_download_token(review_id, TOKEN_TTL_SECONDS)

    # Log successful authorization
    from ..models.review import AuditLogEntry
    from datetime import datetime

    review.add_audit_log(AuditLogEntry(
        timestamp=datetime.utcnow().isoformat(),
        action="authorize_success",
        actor="manager",
        ip_address=get_client_ip(request),
        details=f"Download token issued, expires in {TOKEN_TTL_SECONDS}s"
    ))
    storage.save(review)

    base_url = str(request.base_url).rstrip("/")
    download_url = f"{base_url}/manager/reviews/{review_id}/download?token={token.token}"

    return AuthorizeResponse(
        success=True,
        token=token.token,
        download_url=download_url,
        expires_in_seconds=TOKEN_TTL_SECONDS
    )


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
        actor="manager",
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
