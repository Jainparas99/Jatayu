# ruff: noqa: E501
import hashlib
import io
import json
import tarfile

import pytest

from unpinned.parse import Patch
from unpinned.verify import harness
from unpinned.verify.agent import _prefixes

URL = "https://github.com/acme/app"
COMMIT = "a" * 40
SHA = hashlib.sha256(b"probe").hexdigest()
CASE = harness.SecurityCase(cve="CVE-2026-87975", path="security_probe.py", sha256=SHA)

JUNIT_OK = b"""<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="workboard.tests.CardTests-20261025" tests="2" file="workboard/tests.py"
             time="0.01" timestamp="2026-10-25T14:00:00" failures="0" errors="0" skipped="0">
    <testcase classname="workboard.tests.CardTests" name="test_a" time="0.001" file="workboard/tests.py" line="5"/>
    <testcase classname="workboard.tests.CardTests" name="test_b" time="0.001" file="workboard/tests.py" line="9">
      <system-out><![CDATA[ok]]></system-out>
    </testcase>
  </testsuite>
</testsuites>"""

JUNIT_FAIL = JUNIT_OK.replace(b'failures="0"', b'failures="1"').replace(
    b'line="9">', b'line="9"><failure type="AssertionError" message="boom">Traceback x</failure>'
)


def _probe_out(outcome: str, version: str) -> bytes:
    return json.dumps(
        {
            "case": "CVE-2026-87975 editable-primary-key formset regression",
            "probe_sha256": SHA,
            "django_version": version,
            "outcome": outcome,
            "benign_control_passed": True,
            "http_status": 200,
        }
    ).encode()


def _art(bundle, **over):
    art = {
        "DONE": b"done\n",
        "head.txt": (COMMIT + "\n").encode(),
        "python.txt": b"Python 3.12.3\n",
        "django.txt": b"5.2.18\n",
        "install.exit": b"0\n",
        "tests.exit": b"0\n",
        "junit.xml": JUNIT_OK,
        "check.exit": b"0\n",
        "probe.sha256": (SHA + "\n").encode(),
        "probe.exit": b"0\n",
        "probe.stdout": _probe_out("blocked", "5.2.18"),
    }
    art.update(over)
    return {k: v for k, v in art.items() if v is not None}


def _returned(bundle):
    return {
        "verify.sh": bundle.script.encode(),
        "patch.tar.gz": bundle.patch_tgz,
        "deletes.txt": bundle.deletes.encode(),
    }


def _report(bundle, art, returned=None, version="5.2.18"):
    return harness.report_from_artifacts(
        art,
        bundle=bundle,
        returned=_returned(bundle) if returned is None else returned,
        commit=COMMIT,
        django_version=version,
        case=CASE,
    )


def test_build_mounts_script_patch_and_deletes():
    patch = Patch(files={"app/models.py": "x = 1\n"}, deletes=["old.py"])
    b = harness.build(URL, COMMIT, "5.2.18", patch, CASE)
    assert [s["target"] for s in b.sources] == [
        "jatayu/verify.sh",
        "jatayu/patch.tar.gz",
        "jatayu/deletes.txt",
    ]
    assert all(s["type"] == "inline" and s["encoding"] == "base64" for s in b.sources)
    with tarfile.open(fileobj=io.BytesIO(b.patch_tgz)) as t:
        assert t.getnames() == ["app/models.py"]
    assert b.deletes == "old.py\n"
    assert COMMIT in b.script and "Django==5.2.18" in b.script and "security_probe.py" in b.script


@pytest.mark.parametrize(
    "args",
    [
        ("https://evil.example/x", COMMIT, "5.2.18"),
        (URL, "HEAD", "5.2.18"),
        (URL, COMMIT, "5.2; rm -rf /"),
    ],
)
def test_build_rejects_unsafe_inputs(args):
    with pytest.raises(ValueError):
        harness.build(*args, None, CASE)


def test_patch_may_not_touch_the_frozen_probe():
    with pytest.raises(ValueError, match="frozen security probe"):
        harness.build(URL, COMMIT, "5.2.18", Patch(files={"security_probe.py": "x"}), CASE)


def test_complete_artifacts_are_verified():
    b = harness.build(URL, COMMIT, "5.2.18", Patch(), CASE)
    r = _report(b, _art(b))
    assert r.artifacts_verified and r.evidence_source == "sandbox_artifacts"
    assert (r.suite.passed, r.suite.failed, r.tests_exit_code) == (2, 0, 0)
    (e,) = r.exploits
    assert (e.outcome, e.blocked, e.benign_control_passed) == ("blocked", True, True)


def test_failing_tests_are_verified_failures_with_names():
    b = harness.build(URL, COMMIT, "5.2.18", Patch(), CASE)
    r = _report(b, _art(b, **{"junit.xml": JUNIT_FAIL, "tests.exit": b"1\n"}))
    assert r.artifacts_verified and r.suite.failed == 1
    assert r.failures[0].test == "workboard.tests.CardTests.test_b"


def test_startup_crash_without_junit_is_a_verified_error():
    b = harness.build(URL, COMMIT, "5.2.18", Patch(), CASE)
    art = _art(
        b, **{"junit.xml": None, "tests.exit": b"1\n", "tests.stderr": b"TypeError: index_together"}
    )
    r = _report(b, art)
    assert r.artifacts_verified and r.suite.errors == 1 and r.suite.passed == 0
    assert "index_together" in r.failures[0].trace_head


@pytest.mark.parametrize(
    "tamper,expect",
    [
        ({"returned": {}}, "harness script"),
        ({"art": {"head.txt": b"b" * 40}}, "source commit"),
        ({"art": {"django.txt": b"5.2.17"}}, "installed Django"),
        ({"art": {"DONE": None}}, "did not finish"),
        ({"art": {"tests.exit": b"0\n", "junit.xml": None}}, "without a JUnit"),
    ],
)
def test_untrustworthy_artifacts_are_not_verified(tamper, expect):
    b = harness.build(URL, COMMIT, "5.2.18", Patch(), CASE)
    r = _report(b, _art(b, **tamper.get("art", {})), tamper.get("returned"))
    assert not r.artifacts_verified and r.evidence_source == "agent_summary"
    assert expect in r.notes


def test_changed_probe_file_is_never_remediation():
    b = harness.build(URL, COMMIT, "5.2.18", Patch(), CASE)
    r = _report(b, _art(b, **{"probe.sha256": b"0" * 64}))
    (e,) = r.exploits
    assert e.outcome == "error" and not e.blocked


def test_vulnerable_baseline_probe_parses():
    b = harness.build(URL, COMMIT, "4.2.30", None, CASE)
    art = _art(b, **{"django.txt": b"4.2.30", "probe.stdout": _probe_out("vulnerable", "4.2.30")})
    r = _report(b, art, version="4.2.30")
    assert r.artifacts_verified and r.exploits[0].outcome == "vulnerable"


def test_security_case_from_env(monkeypatch):
    monkeypatch.delenv("JATAYU_PROBE_SHA256", raising=False)
    assert harness.SecurityCase.from_env() is None
    monkeypatch.setenv("JATAYU_PROBE_SHA256", SHA)
    assert harness.SecurityCase.from_env().path == "security_probe.py"
    monkeypatch.setenv("JATAYU_PROBE_PATH", "../x.py")
    with pytest.raises(ValueError):
        harness.SecurityCase.from_env()


def test_prefixes_from_reported_dir():
    assert _prefixes("/workspace/jatayu") == ["jatayu", "workspace/jatayu"]
    assert _prefixes(None) == ["jatayu"]


def test_changed_deletion_manifest_is_not_verified():
    b = harness.build(URL, COMMIT, "5.2.18", Patch(deletes=["old.py"]), CASE)
    returned = _returned(b) | {"deletes.txt": b"security_probe.py\n"}
    r = _report(b, _art(b), returned)
    assert not r.artifacts_verified and "deletion manifest" in r.notes
    r = _report(b, _art(b), {k: v for k, v in _returned(b).items() if k != "deletes.txt"})
    assert not r.artifacts_verified


def test_requirements_failure_cannot_be_masked_by_pinned_install():
    b = harness.build(URL, COMMIT, "5.2.18", Patch(), CASE)
    assert 'if [ "$REQ" -ne 0 ]; then rec install.exit "$REQ"' in b.script
