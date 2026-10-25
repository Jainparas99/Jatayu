"""Scan repos (local paths or public GitHub URLs) and rank them by framework-support risk."""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from .detect import Finding, detect
from .eol import CATALOG_AS_OF, LABELS, CycleStatus, status_for

Severity = Literal["critical", "high", "medium", "low", "none"]
_SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "none": 4}


def engine_for(product: str) -> str:
    """Can Jatayu's upgrade engine take this on today?"""
    from ..adapters import REGISTRY, ROADMAP

    if product in REGISTRY:
        return "ready"
    if product in ROADMAP:
        return "roadmap"
    return "generic"


@dataclass
class Component:
    finding: Finding
    status: CycleStatus
    severity: Severity
    label: str
    engine: str


@dataclass
class RepoReport:
    target: str
    commit: str | None
    components: list[Component] = field(default_factory=list)
    error: str | None = None

    @property
    def severity(self) -> Severity:
        if self.error:
            return "none"
        return min((c.severity for c in self.components), key=_SEV_ORDER.get, default="none")

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "commit": self.commit,
            "severity": self.severity,
            "error": self.error,
            "components": [
                {
                    "label": c.label,
                    "engine": c.engine,
                    "severity": c.severity,
                    "finding": asdict(c.finding),
                    "status": asdict(c.status),
                }
                for c in self.components
            ],
        }


def severity_of(s: CycleStatus) -> Severity:
    if s.status == "eol":
        return "critical" if s.days_overdue > 365 else "high"
    if s.status == "expiring":
        return "medium"
    if s.status == "supported":
        return "none" if s.recommended is None else "low"
    return "none"


def _is_url(target: str) -> bool:
    return target.startswith("https://")


def _clone(url: str) -> tuple[Path, str]:
    from ..repository import validate_source

    validate_source(url)
    d = Path(tempfile.mkdtemp(prefix="jatayu-fleet-"))
    subprocess.run(
        ["git", "clone", "--depth", "1", "--filter=blob:limit=1m", "--", url, str(d / "repo")],
        check=True,
        timeout=120,
        capture_output=True,
    )
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=d / "repo", text=True)
    return d / "repo", commit.strip()


def scan_target(target: str, today: date | None = None) -> RepoReport:
    try:
        if _is_url(target):
            root, commit = _clone(target)
        else:
            root = Path(target).expanduser()
            if not root.is_dir():
                raise ValueError(f"not a directory: {target}")
            commit = _local_commit(root)
        report = RepoReport(target=target, commit=commit)
        for fd in detect(root):
            st = status_for(fd.product, fd.version, today)
            report.components.append(
                Component(
                    fd,
                    st,
                    severity_of(st),
                    LABELS.get(fd.product, fd.product),
                    engine_for(fd.product),
                )
            )
        report.components.sort(key=lambda c: _SEV_ORDER[c.severity])
        return report
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        return RepoReport(target=target, commit=None, error=str(e)[:300])


def _local_commit(root: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def scan_many(targets: list[str], today: date | None = None) -> dict:
    reports = [scan_target(t, today) for t in targets]
    reports.sort(key=lambda r: _SEV_ORDER[r.severity])
    comps = [c for r in reports for c in r.components]
    return {
        "scanned_at": datetime.now().isoformat(timespec="seconds"),
        "catalog_as_of": CATALOG_AS_OF,
        "catalog_source": "https://endoflife.date",
        "summary": {
            "repos": len(reports),
            "repos_with_eol": sum(1 for r in reports if r.severity in ("critical", "high")),
            "eol_components": sum(1 for c in comps if c.status.status == "eol"),
            "expiring_components": sum(1 for c in comps if c.status.status == "expiring"),
            "jatayu_ready": sum(
                1 for c in comps if c.engine == "ready" and c.status.status in ("eol", "expiring")
            ),
            "errors": sum(1 for r in reports if r.error),
        },
        "repos": [r.to_dict() for r in reports],
    }


def save(result: dict, runs_dir: Path) -> Path:
    d = runs_dir / "fleet"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"fleet-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(result, indent=1))
    return path


def latest(runs_dir: Path) -> dict | None:
    files = sorted((runs_dir / "fleet").glob("fleet-*.json"))
    return json.loads(files[-1].read_text()) if files else None
