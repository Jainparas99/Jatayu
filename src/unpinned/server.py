"""Deployable Jatayu server: the review API + the Fleet dashboard, with write protection.

Run locally:   uv run uvicorn unpinned.server:app --port 8000
In a container: see Dockerfile and deploy/README.md.

Security model for a remote deployment:
- Reads (GET/HEAD/OPTIONS) are open *to whoever can reach the service*. Put the service
  behind your platform's auth (Cloud Run --no-allow-unauthenticated + IAP, or a VPN).
- Every state-changing request (scan, approve) needs `Authorization: Bearer
  $JATAYU_DASHBOARD_TOKEN`. With no token configured the deployment is read-only.
- Approve still goes through review gates in api.py; this layer only decides who may ask.
"""

from __future__ import annotations

import hmac
import os

from fastapi import Request
from fastapi.responses import JSONResponse

from .api import app
from .fleet.routes import router as fleet_router

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

app.include_router(fleet_router)


@app.middleware("http")
async def require_token_for_writes(request: Request, call_next):
    if request.method in SAFE_METHODS:
        return await call_next(request)
    expected = os.getenv("JATAYU_DASHBOARD_TOKEN", "")
    if not expected:
        return JSONResponse(
            {"detail": "Read-only deployment. Set JATAYU_DASHBOARD_TOKEN to enable actions."},
            status_code=403,
        )
    supplied = request.headers.get("authorization", "")
    if not hmac.compare_digest(supplied.encode(), f"Bearer {expected}".encode()):
        return JSONResponse({"detail": "Missing or wrong bearer token."}, status_code=401)
    return await call_next(request)
