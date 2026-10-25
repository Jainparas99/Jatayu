from unpinned.models import ExploitResult, Failure, Iteration, RunSummary, SuiteCounts, VerifyReport
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


def test_unverified_deprecation_claims_are_hidden():
    run = _run("b0", 999, 0, True)
    run.final.artifacts_verified = False
    run.final.deprecation_warnings = 0
    run.final.django_version = "5.2.18"
    row = rows([run])[0]
    assert row["deprecations"] == "unverified"
    assert row["version"] == "unverified"


def test_baseline_is_visible_when_migration_has_not_recorded_a_result():
    run = _run("unpinned", 25, 0, False)
    run.baseline_report = run.final.model_copy(deep=True)
    run.baseline_report.django_version = "4.2.30"
    run.iterations = []
    run.wall_seconds = 73.6
    before, after = rows([run])
    assert before["run"] == "Before upgrade"
    assert before["tests"] == "25/25" and before["version"] == "4.2.30"
    assert before["wall_s"] == "-"  # no baseline-specific timer was recorded
    assert after["tests"] == "not recorded" and after["evidence"] == "not recorded"
    assert after["iterations"] == 0


def test_startup_crash_is_not_presented_as_an_executed_test():
    run = _run("b0", 0, 0, False)
    run.final.suite.errors = 1
    run.final.tests_exit_code = 1
    run.final.failures = [Failure(test="test run did not start", trace_head="index_together")]
    assert rows([run])[0]["tests"] == "not started"


def test_real_testcase_error_keeps_its_recorded_count():
    run = _run("b0", 0, 0, False)
    run.final.suite.errors = 1
    run.final.failures = [Failure(test="workboard.tests.test_save", trace_head="database")]
    assert rows([run])[0]["tests"] == "0/1"


def test_missing_check_status_is_not_zero_issues():
    run = _run("b0", 25, 0, False)
    run.final.checks_exit_code = None
    assert rows([run])[0]["check_issues"] == "not recorded"
    run.final.checks_exit_code = 2
    assert rows([run])[0]["check_issues"] == "failed (exit 2)"


def test_local_fixture_is_labeled_and_cannot_supply_product_metrics():
    run = _run("unpinned", 25, 0, True)
    run.final.evidence_source = "local_fixture"
    run.final.deprecation_warnings = 0
    row = rows([run])[0]
    assert row["evidence"] == "local fixture (not sandbox)"
    for key in ("tests", "check_issues", "deprecations", "exploits_blocked"):
        assert row[key] == "unverified"


def test_both_trust_fields_are_required():
    run = _run("b0", 25, 0, False)
    run.final.artifacts_verified = False
    assert rows([run])[0]["evidence"] == "unverified sandbox artifacts"
    assert rows([run])[0]["tests"] == "unverified"


def test_before_and_after_use_their_own_recorded_versions():
    run = _run("unpinned", 25, 0, True)
    run.final.django_version = "5.2.18"
    run.baseline_report = run.final.model_copy(deep=True)
    run.baseline_report.django_version = "4.2.30"
    before, after = rows([run])
    assert before["version"] == "4.2.30" and after["version"] == "5.2.18"
    assert before["deprecations"] == "-"  # unavailable is distinct from measured zero


def test_generic_versions_are_not_labeled_unverified_or_django():
    run = _run("unpinned", 49, 0, False)
    run.framework = "Express"
    run.scope = "tests_only"
    run.final.framework = "Express"
    run.final.framework_version = "5.3.0"
    run.final.security_assessed = False
    run.final.exploits = []
    run.baseline_report = run.final.model_copy(deep=True)
    run.baseline_report.framework_version = "4.21.2"
    before, after = rows([run])
    assert before["framework"] == after["framework"] == "Express"
    assert before["version"] == "4.21.2" and after["version"] == "5.3.0"
    assert before["tests"] == after["tests"] == "49/49"
    assert before["exploits_blocked"] == after["exploits_blocked"] == "not assessed"


def test_untrusted_generic_version_is_still_hidden():
    run = _run("unpinned", 49, 0, False)
    run.final.framework = "Express"
    run.final.framework_version = "5.3.0"
    run.final.artifacts_verified = False
    assert rows([run])[0]["version"] == "unverified"


def test_tests_only_scope_cannot_imply_security_remediation():
    run = _run("unpinned", 49, 0, True)
    run.scope = "tests_only"
    assert rows([run])[0]["exploits_blocked"] == "not assessed"
