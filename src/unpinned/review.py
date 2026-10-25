"""Review saved evidence against the exact patch currently on disk."""

import json

from .loop import verification_blockers
from .models import RunSummary
from .parse import Patch, patch_digest, unified_diff
from .runs import run_file


def load_summary(run_id: str) -> RunSummary:
    return RunSummary.model_validate_json(run_file(run_id, "summary.json").read_text())


def review_state(run_id: str) -> dict:
    summary = load_summary(run_id)
    blockers = []
    if summary.kind != "unpinned":
        blockers.append("Comparison runs cannot be approved for publication.")
    if summary.final is None:
        blockers.append("No completed verification exists.")
    else:
        blockers.extend(verification_blockers(summary.final, summary.baseline_report))
    digest = None
    diff = ""
    try:
        data = json.loads(run_file(run_id, "patch.json").read_text())
        patch = Patch(**data)
        digest = patch_digest(patch)
        # Store original contents to show a real diff; never invent empty originals.
        originals = json.loads(run_file(run_id, "originals.json").read_text())
        changes = []
        for path in sorted(set(patch.files) | set(patch.deletes)):
            if path not in originals:
                raise ValueError(f"Original content missing for {path}")
            changes.append(unified_diff(path, originals[path], patch.files.get(path, "")))
        diff = "".join(changes)
        if summary.final and summary.final.patch_sha256 != digest:
            blockers.append("Current patch differs from the verified patch.")
    except (OSError, TypeError, ValueError) as exc:
        blockers.append(f"Patch review unavailable: {exc}")
    if not summary.source_commit:
        blockers.append("Immutable source commit missing.")
    elif summary.final and summary.final.source_commit != summary.source_commit:
        blockers.append("Evidence does not match the selected source commit.")
    return {
        "run_id": run_id,
        "patch_sha256": digest,
        "diff": diff,
        "ready_for_review": not blockers,
        "blockers": blockers,
        "publication_available": False,
    }
