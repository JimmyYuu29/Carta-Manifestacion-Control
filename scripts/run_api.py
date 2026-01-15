#!/usr/bin/env python3
"""
Run Review API Server
Ejecutar servidor de API de revision

Usage:
    python scripts/run_api.py
    # or
    uvicorn api.app:app --reload --port 8000

Environment variables:
    MANAGER_PASSWORD: Manager password for download authorization (dev only)
    MANAGER_PASSWORD_HASH: SHA-256 hash of manager password (production)
    DOWNLOAD_TOKEN_TTL: Token TTL in seconds (default: 300)
    HOST: Server host (default: 0.0.0.0)
    PORT: Server port (default: 8000)
    CORS_ORIGINS: Comma-separated allowed origins (default: *)
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def main():
    import uvicorn

    # Set default environment variables if not set
    if not os.environ.get("MANAGER_PASSWORD") and not os.environ.get("MANAGER_PASSWORD_HASH"):
        # Development default password
        print("WARNING: Using default development password. Set MANAGER_PASSWORD_HASH for production!")
        os.environ["MANAGER_PASSWORD"] = "manager123"

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    reload = os.environ.get("RELOAD", "true").lower() == "true"

    print(f"""
    ==========================================
    Carta Manifestacion - Review API Server
    ==========================================

    Server running at: http://{host}:{port}
    API Documentation: http://{host}:{port}/api/docs

    Endpoints:
    - POST   /reviews                      Create new review
    - GET    /reviews/{{id}}/preview        HTML preview
    - GET    /reviews/{{id}}/data           Get review data
    - PATCH  /reviews/{{id}}/data           Update data (whitelist only)
    - POST   /reviews/{{id}}/submit         Submit for approval

    - GET    /manager/reviews/{{id}}         Manager entry page
    - POST   /manager/reviews/{{id}}/authorize  Authorize download
    - GET    /manager/reviews/{{id}}/download   Download Word (with token)

    Press Ctrl+C to stop.
    ==========================================
    """)

    uvicorn.run(
        "api.app:app",
        host=host,
        port=port,
        reload=reload
    )


if __name__ == "__main__":
    main()
