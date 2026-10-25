"""FastAPI control surface (SPEC §10). Not the product: stages, numbers, diffs, Approve. [CP4]"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from .adapters import REGISTRY, ROADMAP
from .config import ROOT, settings
from .models import RunSummary
from .pr import open_pr
from .report import markdown, rows
from .review import load_summary, review_state
from .runs import run_path

app = FastAPI(title="Jatayu")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(ROOT / "static" / "index.html")


def _summaries() -> list[RunSummary]:
    out = []
    for p in sorted(settings().runs_dir.glob("*/summary.json")):
        if not p.resolve().is_relative_to(settings().runs_dir.resolve()):
            continue
        try:
            summary = load_summary(p.parent.name)
            if summary.run_id == p.parent.name:
                out.append(summary)
        except (OSError, ValueError):
            continue
    return out


@app.get("/api/config")
def configuration() -> dict:
    """Expose presence flags and safe defaults, never credential values or settings repr."""
    configured = settings()
    return {
        "credentials": {
            "GEMINI_API_KEY": bool(configured.gemini_api_key),
            "GITHUB_TOKEN": bool(configured.github_token),
            "JATAYU_DASHBOARD_TOKEN": bool(os.getenv("JATAYU_DASHBOARD_TOKEN", "")),
        },
        "fork_owner_configured": bool(configured.fork_owner),
        "target_version": configured.target_django,
        "baseline_version": configured.baseline_django,
        "max_iterations": configured.max_iterations,
        "publication_available": False,
        "browser_execution_available": False,
        "read_access": "platform_authentication",
        "write_access": "bearer_token" if os.getenv("JATAYU_DASHBOARD_TOKEN") else "read_only",
    }


@app.get("/api/overview")
def overview() -> dict:
    """Inventory saved runs; re-evaluate gates against each patch currently on disk."""
    inventory = []
    for summary in sorted(_summaries(), key=lambda s: (s.started_at, s.run_id), reverse=True):
        try:
            review = review_state(summary.run_id)
        except (OSError, ValueError, TypeError):
            review = {"ready_for_review": False, "blockers": ["Saved evidence cannot be reviewed."]}
        report = summary.final
        inventory.append(
            {
                "run_id": summary.run_id,
                "kind": summary.kind,
                "repo_url": summary.repo_url,
                "target": summary.target_django,
                "started_at": summary.started_at,
                "status": "ready_for_review" if review["ready_for_review"] else "blocked",
                "blocker_count": len(review["blockers"]),
                "attempts": len(summary.iterations),
                "artifacts_verified": bool(
                    report
                    and report.artifacts_verified
                    and report.evidence_source == "sandbox_artifacts"
                ),
            }
        )
    ready = sum(r["status"] == "ready_for_review" for r in inventory)
    return {
        "version": "0.1.0",
        "runs": inventory,
        "counts": {
            "runs": len(inventory),
            "ready_for_review": ready,
            "blocked": len(inventory) - ready,
            "verified_artifacts": sum(r["artifacts_verified"] for r in inventory),
        },
        "configuration": configuration(),
    }


@app.get("/api/adapters")
def adapters() -> list[dict]:
    descriptions = {
        "django": (
            "Django preparation and migration commands are wired. "
            "Independent cloud verification remains incomplete."
        ),
        "rails": (
            "Rails version bump and adapter contract are on the roadmap. "
            "No verified migration is claimed."
        ),
        "spring-boot": (
            "Spring Boot version bump and adapter contract are on the roadmap. "
            "No verified migration is claimed."
        ),
    }
    out = [
        {
            "name": a.name,
            "framework": a.framework,
            "language": a.language,
            "status": "roadmap" if a.roadmap else "verification_pending",
            "description": descriptions.get(
                a.name, "Roadmap adapter; no verified migration is claimed."
            ),
        }
        for a in [*REGISTRY.values(), *ROADMAP.values()]
    ]
    out.append(
        {
            "name": "generic",
            "framework": "Generic",
            "language": "Any language",
            "status": "preparation_only",
            "description": (
                "Prepare any text repository with explicit versions, commands, and notes. "
                "Cloud execution is unavailable for this adapter."
            ),
        }
    )
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
