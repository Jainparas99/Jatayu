import pytest

from unpinned.loop import is_green, merge
from unpinned.models import ExploitResult, SuiteCounts, VerifyReport
from unpinned.parse import Patch


def test_merge_later_patch_wins_and_undeletes():
    a = Patch(files={"x.py": "1"}, deletes=["y.py"])
    b = Patch(files={"x.py": "2", "y.py": "back"})
    m = merge(a, b)
    assert m.files == {"x.py": "2", "y.py": "back"} and m.deletes == []


def test_green_requires_tests_and_exploits():
    ok = VerifyReport(suite=SuiteCounts(passed=5))
    assert not is_green(ok)
    bad = VerifyReport(
        suite=SuiteCounts(passed=5),
        exploits=[ExploitResult(cve="C", django_version="5.2", blocked=False)],
    )
    assert not is_green(bad)


def reports():
    before = VerifyReport(
        django_version="4.2.30",
        suite=SuiteCounts(passed=5),
        install_ok=True,
        tests_exit_code=0,
        checks_exit_code=0,
        source_commit="a" * 40,
        artifacts_verified=True,
        evidence_source="sandbox_artifacts",
        exploits=[
            ExploitResult(
                cve="C",
                django_version="4.2.30",
                blocked=False,
                outcome="vulnerable",
                benign_control_passed=True,
                probe_sha256="b" * 64,
            )
        ],
    )
    after = before.model_copy(deep=True)
    after.django_version = "5.2.18"
    after.exploits[0].django_version = "5.2.18"
    after.exploits[0].blocked = True
    after.exploits[0].outcome = "blocked"
    return before, after


def test_complete_independent_before_after_evidence_can_be_green():
    before, after = reports()
    assert is_green(after, before)


@pytest.mark.parametrize(
    "change",
    [
        {"suite": SuiteCounts()},
        {"suite": SuiteCounts(passed=5, skipped=1)},
        {"checks_exit_code": None},
        {"tests_exit_code": 1},
        {"check": ["bad config"]},
        {"exploits": []},
        {"artifacts_verified": False},
        {"source_commit": "c" * 40},
        {"evidence_source": "agent_summary"},
    ],
)
def test_missing_or_failing_evidence_never_goes_green(change):
    before, after = reports()
    assert not is_green(after.model_copy(update=change), before)


def test_updated_deletion_wins_over_earlier_file_edit():
    merged = merge(Patch(files={"app.py": "edit"}), Patch(deletes=["app.py"]))
    assert merged.files == {} and merged.deletes == ["app.py"]
