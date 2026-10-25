"""Before/after tables built ONLY from saved run JSON (AGENTS.md invariant 1)."""

from __future__ import annotations

import json
from pathlib import Path

from .models import RunSummary, VerifyReport

LABELS = {
    "b0": "B0 bump only",
    "b1": "B1 django-upgrade",
    "b2": "B2 Flash file-by-file",
    "unpinned": "Jatayu (Argon)",
}
ORDER = ["b0", "b1", "b2", "unpinned"]


def load_runs(paths: list[Path]) -> list[RunSummary]:
    return [RunSummary.model_validate(json.loads(p.read_text())) for p in paths]


def _row(
    label: str,
    report: VerifyReport | None,
    *,
    iterations: int | str,
    wall_seconds: float | None = None,
    framework: str | None = None,
    scope: str | None = None,
) -> dict:
    measured = bool(
        report and report.artifacts_verified and report.evidence_source == "sandbox_artifacts"
    )
    source = report.evidence_source if report else None
    evidence = (
        "verified sandbox"
        if measured
        else "local fixture (not sandbox)"
        if source == "local_fixture"
        else "unverified sandbox artifacts"
        if source == "sandbox_artifacts"
        else "unverified agent summary"
        if report
        else "not recorded"
    )
    tests = "unverified" if report else "not recorded"
    checks: int | str = "unverified" if report else "not recorded"
    deprecations: int | str = "unverified" if report else "not recorded"
    exploits = "unverified" if report else "not recorded"
    if measured:
        # A harness startup error is not an executed testcase. Do not turn its
        # diagnostic SuiteCounts(errors=1) sentinel into a fabricated 0/1 result.
        not_started = (
            report.suite.passed == 0
            and report.suite.failed == 0
            and any(f.test == "test run did not start" for f in report.failures)
        )
        tests = "not started" if not_started else f"{report.suite.passed}/{report.suite.total}"
        checks = (
            "not recorded"
            if report.checks_exit_code is None
            else len(report.check)
            if report.check or report.checks_exit_code == 0
            else f"failed (exit {report.checks_exit_code})"
        )
        deprecations = "-" if report.deprecation_warnings is None else report.deprecation_warnings
        blocked = sum(e.blocked and e.outcome == "blocked" for e in report.exploits)
        exploits = f"{blocked}/{len(report.exploits)}" if report.exploits else "not recorded"
    if scope == "tests_only" or (report and report.security_assessed is False):
        exploits = "not assessed"
    version = (report.framework_version or report.django_version) if report else None
    return {
        "run": label,
        "framework": (report.framework if report else None) or framework or "Django",
        "version": version if measured and version else "unverified" if report else "not recorded",
        "evidence": evidence,
        "tests": tests,
        "check_issues": checks,
        "deprecations": deprecations,
        "exploits_blocked": exploits,
        "iterations": iterations,
        # Timing is measured by the controller, separately from sandbox test metrics.
        "wall_s": "-" if wall_seconds is None else round(wall_seconds),
    }


def rows(runs: list[RunSummary]) -> list[dict]:
    out = []
    for r in sorted(runs, key=lambda r: ORDER.index(r.kind) if r.kind in ORDER else 99):
        if r.kind == "unpinned" and r.baseline_report is not None:
            out.append(
                _row(
                    "Before upgrade",
                    r.baseline_report,
                    iterations="-",
                    framework=r.framework,
                    scope=r.scope,
                )
            )
        out.append(
            _row(
                LABELS.get(r.kind, r.kind),
                r.final,
                iterations=len(r.iterations),
                wall_seconds=r.wall_seconds,
                framework=r.framework,
                scope=r.scope,
            )
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
