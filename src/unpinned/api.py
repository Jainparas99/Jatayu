"""FastAPI control surface (SPEC §10). Not the product: stages, numbers, diffs, Approve. [CP4]"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError

from .config import ROOT, settings
from .models import RunSummary
from .pr import open_pr
from .report import markdown, rows
from .review import load_summary, review_state
from .runs import run_path

app = FastAPI(title="Jatayu")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(ROOT / "static" / "index.html")


def _summaries() -> list[RunSummary]:
    out = []
    for p in sorted(settings().runs_dir.glob("*/summary.json")):
        if not p.resolve().is_relative_to(settings().runs_dir.resolve()):
            continue
        try:
            out.append(load_summary(p.parent.name))
        except (OSError, ValueError):
            continue
    return out


@app.get("/api/runs")
def list_runs() -> list[dict]:
    return [s.model_dump(mode="json") for s in _summaries()]


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    try:
        return load_summary(run_id).model_dump(mode="json")
    except FileNotFoundError as exc:
        raise HTTPException(404, "Run not found") from exc
    except (ValueError, ValidationError) as exc:
        raise HTTPException(422, "Invalid run or saved summary") from exc


@app.get("/api/runs/{run_id}/review")
def get_review(run_id: str) -> dict:
    try:
        run_path(run_id)
        return review_state(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "Run not found") from exc
    except ValueError as exc:
        raise HTTPException(422, "Invalid run") from exc


@app.get("/api/table")
def table() -> dict:
    runs = _summaries()
    return {"rows": rows(runs), "markdown": markdown(runs)}


class Approval(BaseModel):
    patch_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


@app.post("/api/runs/{run_id}/approve")
def approve(run_id: str, approval: Approval) -> dict:
    """The only endpoint allowed to cause an external side effect."""
    try:
        return {
            "pr_url": open_pr(run_id, approved_by_human=True, patch_sha256=approval.patch_sha256)
        }
    except FileNotFoundError as e:
        raise HTTPException(404, "Run not found") from e
    except (PermissionError, ValueError) as e:
        raise HTTPException(409, str(e)) from e
    except NotImplementedError as e:
        raise HTTPException(501, str(e)) from e
