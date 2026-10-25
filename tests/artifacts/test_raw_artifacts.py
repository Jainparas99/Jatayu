"""Adversarial raw artifacts must not turn failed verification into success."""

import json

import pytest

from unpinned.artifacts import ArtifactError, parse_django_probe, parse_junit


def test_junit_counts_cases_instead_of_trusting_summary():
    counts = parse_junit("""<testsuites tests="4" failures="1" errors="1" skipped="1">
      <testsuite tests="4" failures="1" errors="1" skipped="1">
        <testcase classname="app" name="pass"/>
        <testcase classname="app" name="fail"><failure message="no"/></testcase>
        <testcase classname="app" name="setup"><error message="setup failed"/></testcase>
        <testcase classname="app" name="skip"><skipped/></testcase>
      </testsuite></testsuites>""")
    assert counts.model_dump() == {"passed": 1, "failed": 1, "errors": 1, "skipped": 1}


def test_junit_nested_suites_are_counted_once():
    counts = parse_junit("""<testsuites tests="2"><testsuite tests="2">
      <testsuite tests="1"><testcase classname="a" name="same"/></testsuite>
      <testsuite tests="1"><testcase classname="b" name="same"/></testsuite>
    </testsuite></testsuites>""")
    assert counts.total == counts.passed == 2


def test_empty_junit_stays_empty():
    assert parse_junit('<testsuite tests="0"/>').total == 0


@pytest.mark.parametrize(
    "xml",
    [
        '<testsuite tests="99"><testcase name="one"/></testsuite>',
        '<testsuite failures="0"><testcase name="one"><failure/></testcase></testsuite>',
        '<testsuites tests="9"><testsuite><testcase name="one"/></testsuite></testsuites>',
        '<testsuite tests="-1"/>',
        '<testsuite tests="NaN"/>',
        '<testsuite><testcase name="x"/><testcase name="x"/></testsuite>',
        "<testsuite><testcase/></testsuite>",
        '<testsuite><testcase name="x"><failure/><skipped/></testcase></testsuite>',
        '<testsuite><testcase name="x"><error/><error/></testcase></testsuite>',
        '<testsuite><testcase name="x"><rerunFailure/></testcase></testsuite>',
        '<testsuite><testcase name="x" status="notrun"/></testsuite>',
        '<testsuite><testcase name="x" result="suppressed"/></testsuite>',
        '<testsuite disabled="1"><testcase name="x"/></testsuite>',
        '<testsuite><error message="collection failed"/></testsuite>',
        '<testsuites><testcase name="x"/></testsuites>',
        '<report tests="12"/>',
        "<testsuite>",
        '<!DOCTYPE testsuite [<!ENTITY x "expanded">]><testsuite>&x;</testsuite>',
    ],
)
def test_junit_rejects_ambiguous_or_forged_counts(xml):
    with pytest.raises(ArtifactError):
        parse_junit(xml)


@pytest.mark.parametrize("encoding", ["utf-16", "utf-16-le", "utf-16-be"])
def test_junit_rejects_non_utf8_and_oversized_documents(monkeypatch, encoding):
    with pytest.raises(ArtifactError):
        parse_junit("<testsuite/>".encode(encoding))
    monkeypatch.setattr("unpinned.artifacts.parse.MAX_ARTIFACT_BYTES", 5)
    with pytest.raises(ArtifactError):
        parse_junit("<testsuite/>")


def test_junit_limits_cases(monkeypatch):
    monkeypatch.setattr("unpinned.artifacts.parse.MAX_TEST_CASES", 1)
    with pytest.raises(ArtifactError):
        parse_junit('<testsuite><testcase name="a"/><testcase name="b"/></testsuite>')


def test_junit_rejects_huge_declared_counts_without_integer_conversion():
    with pytest.raises(ArtifactError):
        parse_junit('<testsuite tests="' + "9" * 5000 + '"/>')


@pytest.fixture
def probe():
    return {
        "case": "CVE-2026-87975 editable-primary-key formset regression",
        "django_version": "5.2.18",
        "probe_sha256": "a" * 64,
        "outcome": "blocked",
        "benign_control_passed": True,
        "http_status": 200,
    }


def parse_probe(raw, **overrides):
    options = {
        "exit_code": 0,
        "expected_cve": "CVE-2026-87975",
        "expected_version": "5.2.18",
        "expected_sha256": "a" * 64,
    }
    return parse_django_probe(raw, **(options | overrides))


@pytest.mark.parametrize("outcome", ["vulnerable", "blocked", "error", "timeout", "skipped"])
def test_probe_preserves_inconclusive_outcomes(probe, outcome):
    probe["outcome"] = outcome
    result = parse_probe(json.dumps(probe))
    assert result.outcome == outcome
    assert result.blocked == (outcome == "blocked")


@pytest.mark.parametrize(
    "changes",
    [
        {"case": "CVE-2026-879750 different case"},
        {"probe_sha256": "b" * 64},
        {"django_version": "4.2.30"},
        {"outcome": "success"},
        {"outcome": []},
        {"benign_control_passed": "true"},
        {"benign_control_passed": 1},
        {"http_status": 500},
        {"http_status": "200"},
    ],
)
def test_probe_rejects_mismatched_or_ambiguous_evidence(probe, changes):
    with pytest.raises(ArtifactError):
        parse_probe(json.dumps(probe | changes))


@pytest.mark.parametrize("code", [1, -9, None, False])
def test_successful_looking_stdout_cannot_override_failed_process(probe, code):
    with pytest.raises(ArtifactError):
        parse_probe(json.dumps(probe), exit_code=code)


@pytest.mark.parametrize(
    "raw", ["[]", "null", "{}", "not JSON", '{"outcome":"error","outcome":"blocked"}']
)
def test_probe_requires_one_unambiguous_json_object(raw):
    with pytest.raises(ArtifactError):
        parse_probe(raw)


def test_false_benign_control_is_retained_for_gate_to_reject(probe):
    result = parse_probe(json.dumps(probe | {"benign_control_passed": False}))
    assert result.benign_control_passed is False


def test_model_trust_fields_cannot_grant_provenance(probe):
    result = parse_probe(
        json.dumps(probe | {"artifacts_verified": True, "evidence_source": "sandbox_artifacts"})
    )
    assert "artifacts_verified" not in result.model_dump()
    assert "evidence_source" not in result.model_dump()
