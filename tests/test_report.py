from unpinned.models import ExploitResult, Iteration, RunSummary, SuiteCounts, VerifyReport
from unpinned.report import markdown, rows


def _run(kind, passed, failed, blocked):
    rep = VerifyReport(
        suite=SuiteCounts(passed=passed, failed=failed),
        exploits=[
            ExploitResult(
                cve="CVE-X",
                django_version="5.2.18",
                blocked=blocked,
                outcome="blocked" if blocked else "vulnerable",
            )
        ],
        artifacts_verified=True,
        evidence_source="sandbox_artifacts",
    )
    return RunSummary(
        run_id=kind,
        kind=kind,
        repo_url="u",
        target_django="5.2.18",
        started_at="t",
        iterations=[Iteration(n=1, report=rep)],
    )


def test_rows_come_from_reports_in_order():
    rs = rows([_run("unpinned", 10, 0, True), _run("b0", 2, 8, False)])
    assert [r["run"] for r in rs] == ["B0 bump only", "Jatayu (Argon)"]
    assert rs[0]["tests"] == "2/10" and rs[1]["exploits_blocked"] == "1/1"


def test_markdown_empty():
    assert markdown([]) == "_No runs yet._"


def test_agent_summary_is_not_presented_as_measured_results():
    run = _run("unpinned", 999, 0, True)
    run.final.artifacts_verified = False
    row = rows([run])[0]
    assert row["tests"] == "unverified"
    assert row["exploits_blocked"] == "unverified"
