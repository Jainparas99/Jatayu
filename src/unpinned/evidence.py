"""Conservative decision gate. Inputs must come from a trusted test runner."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class RunEvidence:
    tests_collected: int
    tests_passed: int
    tests_exit_code: int
    checks_passed: bool
    benign_control_passed: bool
    probe: Literal["vulnerable", "blocked", "error", "timeout", "skipped"]
    probe_sha256: str


def review_blockers(before: RunEvidence, after: RunEvidence) -> list[str]:
    """Return blockers; an empty list means ready for human review, not publish."""
    blockers = []
    for label, run in (("before", before), ("after", after)):
        if (
            run.tests_collected <= 0
            or run.tests_exit_code != 0
            or run.tests_passed != run.tests_collected
        ):
            blockers.append(f"{label}: application suite is not fully passing")
        if not run.checks_passed:
            blockers.append(f"{label}: required checks failed")
        if not run.benign_control_passed:
            blockers.append(f"{label}: benign control failed")
    if before.probe != "vulnerable":
        blockers.append("baseline vulnerability was not reproduced")
    if after.probe != "blocked":
        blockers.append("post-migration remediation was not established")
    if (
        not before.probe_sha256
        or before.probe_sha256 != after.probe_sha256
        or len(before.probe_sha256) != 64
        or any(c not in "0123456789abcdef" for c in before.probe_sha256)
    ):
        blockers.append("independent probe hash is missing, invalid or changed")
    return blockers
