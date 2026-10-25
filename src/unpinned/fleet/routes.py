"""HTTP routes for the Fleet page. Mounted by unpinned.server (the deployable app)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from ..config import ROOT, settings
from ..repository import validate_source
from .scan import latest, save, scan_many

router = APIRouter()
MAX_TARGETS = 25


class ScanRequest(BaseModel):
    # Over HTTP only public GitHub URLs are accepted: never local paths, so a deployed
    # server can't be used to read its own filesystem.
    targets: list[str] = Field(min_length=1, max_length=MAX_TARGETS)

    @field_validator("targets")
    @classmethod
    def _github_only(cls, v: list[str]) -> list[str]:
        out = []
        for t in v:
            t = t.strip()
            validate_source(t)
            out.append(t)
        return out


@router.get("/fleet")
def fleet_page() -> FileResponse:
    return FileResponse(ROOT / "static" / "fleet.html")


@router.get("/api/fleet/latest")
def fleet_latest() -> dict:
    result = latest(settings().runs_dir)
    if result is None:
        raise HTTPException(404, "No fleet scan yet. Run: python -m unpinned.fleet scan ... --save")
    return result


@router.post("/api/fleet/scan")
def fleet_scan(req: ScanRequest) -> dict:
    result = scan_many(req.targets)
    save(result, settings().runs_dir)
    return result


@router.get("/healthz")
def healthz() -> dict:
    return {"ok": True}
