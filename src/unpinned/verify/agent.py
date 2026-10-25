"""VERIFY: run the project's tests + exploit tests in the Antigravity sandbox (SPEC §7). [CP1]

The numbers in VerifyReport are the only numbers Jatayu ever shows.
"""

from __future__ import annotations

from pydantic import ValidationError

from .. import gemini
from ..jsonx import extract_json
from ..models import VerifyReport
from ..parse import Patch, patch_digest, validate_patch
from ..prompts import load


def file_blocks(patch: Patch | None) -> str:
    if patch is None:
        return "(no file changes)"
    validate_patch(patch)
    parts = [f"<<<FILE {p}>>>\n{c}<<<END FILE>>>" for p, c in sorted(patch.files.items())]
    parts += [f"<<<DELETE {p}>>>" for p in patch.deletes]
    return "\n".join(parts) or "(no file changes)"


def security_test_blocks() -> str:
    return "(No approved target-specific security probes supplied.)"


def spike(repo_url: str, django_version: str) -> dict:
    """Kickoff spike: can this repo install and run its tests in the sandbox?"""
    from ..repository import validate_django_version, validate_source

    validate_source(repo_url)
    validate_django_version(django_version)
    res = gemini.run_agent(load("spike", repo_url=repo_url, django_version=django_version))
    return extract_json(res.text) | {
        "_interaction_id": res.id,
        "_environment_id": res.environment_id,
    }


def verify(
    repo_url: str,
    django_version: str,
    patch: Patch | None,
    test_command: str = "auto-detect (manage.py test or pytest)",
    previous_interaction_id: str | None = None,
    environment_id: str | None = None,
    source_commit: str = "",
) -> tuple[VerifyReport, gemini.Result]:
    from ..repository import validate_django_version, validate_source

    validate_source(repo_url, source_commit)
    validate_django_version(django_version)
    prompt = load(
        "verify",
        repo_url=repo_url,
        django_version=django_version,
        test_command=test_command,
        security_tests=security_test_blocks(),
        file_changes=file_blocks(patch),
        source_commit=source_commit,
    )
    res = gemini.run_agent(
        prompt, previous_interaction_id=previous_interaction_id, environment_id=environment_id
    )
    try:
        report = VerifyReport.model_validate(extract_json(res.text))
    except (ValueError, ValidationError):
        # One repair retry on malformed output, same sandbox session.
        res = gemini.run_agent(
            "Your last reply was not valid JSON for the required schema. "
            "Reply again with ONLY the JSON object.",
            previous_interaction_id=res.id,
            environment_id=res.environment_id,
        )
        report = VerifyReport.model_validate(extract_json(res.text))
    # A model cannot certify its own summary by setting trusted fields in JSON.
    report.artifacts_verified = False
    report.evidence_source = "agent_summary"
    report.source_commit = source_commit
    report.patch_sha256 = patch_digest(patch or Patch())
    return report, res
