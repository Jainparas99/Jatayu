"""VERIFY ↔ FIX loop until green or max iterations (SPEC §4 step 5). [CP3]"""

from __future__ import annotations

import time

from .config import settings
from .evidence import RunEvidence, review_blockers
from .migrate import fix
from .models import Iteration, RunSummary, VerifyReport
from .parse import Patch, patch_digest, validate_patch
from .runs import run_dir, save_json, save_text
from .verify.agent import verify


def merge(base: Patch, update: Patch) -> Patch:
    validate_patch(base)
    validate_patch(update)
    out = Patch(
        files={**base.files, **update.files},
        deletes=sorted(set(base.deletes) | set(update.deletes)),
        summary={**base.summary, **update.summary},
        rejected=base.rejected + update.rejected,
        truncated=base.truncated or update.truncated,
    )
    for p in update.files:
        if p in out.deletes:
            out.deletes.remove(p)
    for p in update.deletes:
        out.files.pop(p, None)
    return out


def verification_blockers(r: VerifyReport, before: VerifyReport | None = None) -> list[str]:
    if before is None:
        return ["baseline evidence is missing"]
    blockers = []
    for label, report in (("before", before), ("after", r)):
        if not report.install_ok or not report.artifacts_verified:
            blockers.append(f"{label}: installation or independent artifact verification missing")
        if report.evidence_source != "sandbox_artifacts":
            blockers.append(f"{label}: not verified sandbox evidence")
    if not r.source_commit or before.source_commit != r.source_commit:
        blockers.append("baseline and result must use the same immutable source commit")
    old = {e.cve: e for e in before.exploits}
    new = {e.cve: e for e in r.exploits}
    if (
        not old
        or old.keys() != new.keys()
        or len(old) != len(before.exploits)
        or len(new) != len(r.exploits)
    ):
        return blockers + ["required security cases are missing, changed or duplicated"]
    for cve in old:

        def evidence(report, exploit):
            return RunEvidence(
                tests_collected=report.suite.total,
                tests_passed=report.suite.passed,
                tests_exit_code=report.tests_exit_code
                if report.tests_exit_code is not None
                else -1,
                checks_passed=report.checks_exit_code == 0 and not report.check,
                benign_control_passed=exploit.benign_control_passed,
                probe=exploit.outcome,
                probe_sha256=exploit.probe_sha256,
            )

        blockers.extend(
            f"{cve}: {b}"
            for b in review_blockers(evidence(before, old[cve]), evidence(r, new[cve]))
        )
        if not new[cve].blocked or old[cve].blocked:
            blockers.append(f"{cve}: blocked flag contradicts the before/after proof")
        if (
            new[cve].django_version != r.django_version
            or old[cve].django_version != before.django_version
        ):
            blockers.append(f"{cve}: Django version does not match its test environment")
    return blockers


def is_green(r: VerifyReport, before: VerifyReport | None = None) -> bool:
    return not verification_blockers(r, before)


def failures_text(r: VerifyReport) -> str:
    lines = [f"suite: {r.suite.model_dump()}"]
    lines += [f"- {f.test}\n{f.trace_head}" for f in r.failures[:40]]
    lines += [f"- manage.py check: {c}" for c in r.check]
    lines += [f"- exploit {e.cve} NOT blocked: {e.evidence}" for e in r.exploits if not e.blocked]
    return "\n".join(lines)


def run_loop(
    summary: RunSummary,
    patch: Patch,
    migrate_interaction_id: str,
    known_files: dict[str, str],
) -> tuple[RunSummary, Patch]:
    s = settings()
    d = run_dir(summary.run_id)
    last_id = migrate_interaction_id
    validate_patch(patch)
    for n in range(1, s.max_iterations + 1):
        t0 = time.monotonic()
        report, res = verify(
            summary.repo_url,
            summary.target_django,
            patch,
            source_commit=summary.source_commit,
            artifact_dir=d / "artifacts" / f"verify-{n}",
        )
        print(
            f"VERIFY {n}: {report.suite.passed} passed, {report.suite.failed} failed, "
            f"{report.suite.errors} errors; evidence={report.evidence_source}; "
            f"probe={[e.outcome for e in report.exploits]}",
            flush=True,
        )
        it = Iteration(
            n=n,
            interaction_id=res.id,
            environment_id=res.environment_id,
            files_changed=len(patch.files) + len(patch.deletes),
            report=report,
            wall_seconds=time.monotonic() - t0,
        )
        summary.iterations.append(it)
        save_json(d / f"verify-{n}.json", report)
        save_text(d / f"verify-{n}.raw.txt", res.text)
        summary.review_blockers = verification_blockers(report, summary.baseline_report)
        if report.patch_sha256 != patch_digest(patch):
            summary.review_blockers.append("verified patch digest does not match current patch")
        if report.django_version != summary.target_django:
            summary.review_blockers.append("verified Django version differs from the exact target")
        baseline_total = summary.baseline_report.suite.total if summary.baseline_report else 0
        if report.suite.total < baseline_total:
            summary.review_blockers.append(
                f"suite shrank: {report.suite.total} tests ran vs {baseline_total} at baseline"
            )
        save_json(d / "summary.json", summary)
        if not summary.review_blockers or n == s.max_iterations or not report.artifacts_verified:
            break
        known = {**{q: "" for q in patch.files}, **dict(known_files)}
        update, res = fix(failures_text(report), last_id, known)
        last_id = res.id
        patch = merge(patch, update)
    return summary, patch
