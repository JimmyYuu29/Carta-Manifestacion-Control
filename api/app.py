"""
FastAPI Application - Controlled Editing and Preview API
Aplicacion FastAPI - API de Edicion Controlada y Previsualizacion

This is the main entry point for the review system API.
Run with: uvicorn api.app:app --reload
"""

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pathlib import Path
import os

from .routes import review_router, manager_router

# Create FastAPI app
app = FastAPI(
    title="Carta Manifestacion - Controlled Review API",
    description="""
    API for controlled document editing and preview system.

    ## Features
    - Employee creates review from form data
    - Employee can only edit whitelisted fields
    - Employee submits review (freezes it)
    - Manager authorizes with password
    - Manager downloads final Word document

    ## Security
    - No Word download for employees
    - Whitelist-only field updates
    - Server-side password validation
    - Short-lived download tokens
    - Full audit logging
    """,
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for frontend assets (CSS, JS)
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Include routers
app.include_router(review_router)
app.include_router(manager_router)


# Error handlers
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(
        status_code=404,
        content={"detail": "Not found", "path": str(request.url.path)}
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


# Health check
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "carta-manifestacion-review-api"}


# Root redirect to docs
@app.get("/")
async def root():
    return {
        "message": "Carta Manifestacion Review API",
        "docs": "/api/docs",
        "health": "/health"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.app:app",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
        reload=True
    )
