"""Strict observations from JUnit XML and the owned Django probe's JSON stdout."""

from __future__ import annotations

import json
import re
from xml.etree import ElementTree as ET

from ..models import ExploitResult, SuiteCounts

MAX_ARTIFACT_BYTES = 8_000_000
MAX_TEST_CASES = 100_000
_HASH = re.compile(r"[0-9a-f]{64}")


class ArtifactError(ValueError):
    """Missing, malformed or internally inconsistent process evidence."""


def _text(raw: bytes | str) -> str:
    try:
        data = raw.encode("utf-8") if isinstance(raw, str) else raw
        if len(data) > MAX_ARTIFACT_BYTES:
            raise ArtifactError("artifact exceeds the size limit")
        decoded = data.decode("utf-8-sig")
        if "\x00" in decoded:
            raise ArtifactError("artifacts must not contain NUL bytes")
        return decoded
    except UnicodeError as exc:
        raise ArtifactError("artifacts must be UTF-8") from exc


def _declared_counts(node: ET.Element, counts: SuiteCounts) -> None:
    observed = {
        "tests": counts.total,
        "failures": counts.failed,
        "errors": counts.errors,
        "skipped": counts.skipped,
    }
    for name, actual in observed.items():
        value = node.get(name)
        if value is not None and (
            not re.fullmatch(r"[0-9]+", value) or (value.lstrip("0") or "0") != str(actual)
        ):
            raise ArtifactError(f"JUnit {name} count disagrees with testcase records")


def parse_junit(raw: bytes | str) -> SuiteCounts:
    """Count actual testcase records and reject contradictory summary counters.

    Handles pytest's testsuites wrapper and nested suites. Empty suites, setup
    errors, skips and failing process statuses must still block the approval gate;
    this function never makes an approval or provenance decision.
    """
    document = _text(raw)
    # Do not permit entity expansion or external document declarations. Requiring
    # UTF-8 above also prevents UTF-16 bytes from bypassing this check.
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", document, re.IGNORECASE):
        raise ArtifactError("DTD and entity declarations are forbidden")
    try:
        root = ET.fromstring(document)
    except (ET.ParseError, ValueError) as exc:
        raise ArtifactError("malformed JUnit XML") from exc
    if root.tag not in {"testsuite", "testsuites"}:
        raise ArtifactError("JUnit root must be testsuite or testsuites")

    results = {}
    identities = set()
    # Process children before their parents without recursive Python calls.
    for node in reversed(list(root.iter())):
        if node.tag not in {"testsuite", "testsuites"}:
            continue
        if node.get("disabled") not in {None, "0"}:
            raise ArtifactError("disabled tests require explicit skipped testcase records")
        counts = SuiteCounts()
        for child in node:
            if child.tag in {"testsuite", "testsuites"}:
                nested = results[id(child)]
                counts.passed += nested.passed
                counts.failed += nested.failed
                counts.errors += nested.errors
                counts.skipped += nested.skipped
            elif child.tag == "testcase":
                if node.tag != "testsuite":
                    raise ArtifactError("testcase must belong to a testsuite")
                name = child.get("name", "").strip()
                if not name:
                    raise ArtifactError("JUnit testcase has no name")
                if child.get("status") not in {None, "run", "passed"} or child.get(
                    "result"
                ) not in {None, "completed"}:
                    raise ArtifactError("unsupported JUnit testcase status")
                identity = (child.get("classname", ""), child.get("file", ""), name)
                if identity in identities:
                    raise ArtifactError("duplicate JUnit testcase identity")
                identities.add(identity)
                if len(identities) > MAX_TEST_CASES:
                    raise ArtifactError("JUnit exceeds the testcase limit")
                if any(
                    c.tag
                    not in {"failure", "error", "skipped", "properties", "system-out", "system-err"}
                    for c in child
                ):
                    raise ArtifactError("unsupported JUnit testcase record")
                statuses = [c.tag for c in child if c.tag in {"failure", "error", "skipped"}]
                if len(statuses) > 1:
                    raise ArtifactError("testcase has conflicting or repeated outcomes")
                status = statuses[0] if statuses else "passed"
                if status == "failure":
                    counts.failed += 1
                elif status == "error":
                    counts.errors += 1
                elif status == "skipped":
                    counts.skipped += 1
                else:
                    counts.passed += 1
            elif child.tag not in {"properties", "system-out", "system-err"}:
                raise ArtifactError(f"unsupported JUnit suite record: {child.tag}")
        _declared_counts(node, counts)
        results[id(node)] = counts
    return results[id(root)]


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ArtifactError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def parse_django_probe(
    raw: bytes | str,
    *,
    exit_code: int,
    expected_cve: str,
    expected_version: str,
    expected_sha256: str,
) -> ExploitResult:
    """Parse the existing probe format against controller-owned expectations.

    Expectations must come from the frozen probe and selected environment, never
    from the probe's own JSON or a model summary. Nonzero exits cannot prove a
    blocked exploit even if stdout contains a successful-looking JSON object.
    """
    if type(exit_code) is not int or exit_code != 0:
        raise ArtifactError("probe process did not exit successfully")
    if not _HASH.fullmatch(expected_sha256):
        raise ArtifactError("expected frozen probe SHA-256 is invalid")
    if not re.fullmatch(r"CVE-[0-9]{4}-[0-9]{4,}", expected_cve):
        raise ArtifactError("expected CVE identifier is invalid")
    if not re.fullmatch(r"[45]\.2\.[0-9]+", expected_version):
        raise ArtifactError("expected Django version must be exact")
    try:
        value = json.loads(_text(raw), object_pairs_hook=_unique_object)
    except (ValueError, RecursionError) as exc:
        raise ArtifactError("malformed probe JSON") from exc
    if not isinstance(value, dict):
        raise ArtifactError("probe output must be a JSON object")
    case = value.get("case")
    if not isinstance(case, str) or not (
        case == expected_cve or case.startswith(expected_cve + " ")
    ):
        raise ArtifactError("probe case does not match the frozen security case")
    if value.get("probe_sha256") != expected_sha256:
        raise ArtifactError("probe hash differs from the frozen probe")
    if value.get("django_version") != expected_version:
        raise ArtifactError("probe Django version differs from the selected environment")
    outcome = value.get("outcome")
    if not isinstance(outcome, str) or outcome not in {
        "vulnerable",
        "blocked",
        "error",
        "timeout",
        "skipped",
    }:
        raise ArtifactError("probe outcome is missing or invalid")
    benign = value.get("benign_control_passed")
    if type(benign) is not bool:
        raise ArtifactError("benign control must be a JSON boolean")
    if outcome in {"vulnerable", "blocked"} and (
        type(value.get("http_status")) is not int or value["http_status"] != 200
    ):
        raise ArtifactError("probe HTTP failure cannot establish exploit behavior")
    return ExploitResult(
        cve=expected_cve,
        django_version=expected_version,
        blocked=outcome == "blocked",
        outcome=outcome,
        benign_control_passed=benign,
        probe_sha256=expected_sha256,
        evidence="Parsed raw probe stdout; sandbox provenance must be established separately.",
    )
