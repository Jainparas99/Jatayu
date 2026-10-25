"""Before/after tables built ONLY from saved run JSON (AGENTS.md invariant 1)."""

from __future__ import annotations

import json
from pathlib import Path

from .models import RunSummary

LABELS = {
    "b0": "B0 bump only",
    "b1": "B1 django-upgrade",
    "b2": "B2 Flash file-by-file",
    "unpinned": "Jatayu (Argon)",
}
ORDER = ["b0", "b1", "b2", "unpinned"]


def load_runs(paths: list[Path]) -> list[RunSummary]:
    return [RunSummary.model_validate(json.loads(p.read_text())) for p in paths]


def rows(runs: list[RunSummary]) -> list[dict]:
    out = []
    for r in sorted(runs, key=lambda r: ORDER.index(r.kind) if r.kind in ORDER else 99):
        f = r.final
        if f is None:
            continue
        measured = f.artifacts_verified and f.evidence_source == "sandbox_artifacts"
        blocked = sum(e.blocked and e.outcome == "blocked" for e in f.exploits)
        out.append(
            {
                "run": LABELS.get(r.kind, r.kind),
                "evidence": "verified sandbox" if measured else "unverified agent summary",
                "tests": f"{f.suite.passed}/{f.suite.total}" if measured else "unverified",
                "check_issues": len(f.check) if measured else "unverified",
                "deprecations": "-" if f.deprecation_warnings is None else f.deprecation_warnings,
                "exploits_blocked": f"{blocked}/{len(f.exploits)}"
                if measured and f.exploits
                else "unverified",
                "iterations": len(r.iterations),
                "wall_s": "-" if r.wall_seconds is None else round(r.wall_seconds),
            }
        )
    return out


def markdown(runs: list[RunSummary]) -> str:
    rs = rows(runs)
    if not rs:
        return "_No runs yet._"
    cols = list(rs[0].keys())
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(str(r[c]) for c in cols) + " |" for r in rs]
    return "\n".join(lines)
