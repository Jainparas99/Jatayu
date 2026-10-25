"""Baselines measured with the same VERIFY harness (SPEC §5). [CP1 for B0, CP3 for B1/B2]"""

from __future__ import annotations

import re
import subprocess
import time
from datetime import datetime

from .config import settings
from .models import Iteration, RunSummary
from .pack import Bundle
from .parse import Patch
from .runs import new_run_id, run_dir, save_json
from .verify.agent import verify

_PIN = re.compile(r"(?im)^\s*django\s*([<>=!~].*)?$")


def bump_requirements(bundle: Bundle, target: str) -> Patch:
    """B0: only change the Django pin in requirements files."""
    p = Patch()
    for path, content in bundle.files.items():
        if path.endswith(".txt") and "requirements" in path and _PIN.search(content):
            p.files[path] = _PIN.sub(f"Django=={target}", content)
    return p


def _record(kind: str, repo_url: str, patch: Patch, source_commit: str) -> RunSummary:
    s = settings()
    summary = RunSummary(
        run_id=new_run_id(kind),
        kind=kind,
        repo_url=repo_url,
        target_django=s.target_django,
        started_at=datetime.now().isoformat(timespec="seconds"),
    )
    summary.source_commit = source_commit
    t0 = time.monotonic()
    report, res = verify(repo_url, s.target_django, patch, source_commit=source_commit)
    summary.review_blockers = ["Baseline comparison only; not approved migration evidence."]
    summary.iterations.append(
        Iteration(n=1, interaction_id=res.id, files_changed=len(patch.files), report=report)
    )
    summary.wall_seconds = time.monotonic() - t0
    save_json(run_dir(summary.run_id) / "summary.json", summary)
    return summary


def b0(repo_url: str, bundle: Bundle) -> RunSummary:
    source_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=bundle.root, text=True
    ).strip()
    return _record(
        "b0", repo_url, bump_requirements(bundle, settings().target_django), source_commit
    )


def b1(repo_url: str, bundle: Bundle) -> RunSummary:
    raise NotImplementedError(
        "CP3: run `django-upgrade --target-version 5.2` on every .py file "
        "(check its supported targets), plus the bump, then _record('b1', ...)"
    )


def b2(repo_url: str, bundle: Bundle) -> RunSummary:
    raise NotImplementedError(
        "CP3: gemini-3.8-flash per file WITHOUT the rest of the repo, same FILE format, "
        "plus the bump, then _record('b2', ...)"
    )
