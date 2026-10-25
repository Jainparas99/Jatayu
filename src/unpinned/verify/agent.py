"""VERIFY: run the project's tests + the frozen security probe in the Antigravity sandbox.

The sandbox agent only runs a controller-owned script (verify/harness.py). Results come from
raw files downloaded through the Environments Files API, never from the model's reply.
The numbers in VerifyReport are the only numbers Jatayu ever shows.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from .. import gemini
from ..jsonx import extract_json
from ..models import VerifyReport
from ..parse import Patch, patch_digest, validate_patch
from ..prompts import load
from . import harness


def file_blocks(patch: Patch | None) -> str:
    """Kept for prompts/tests that show a patch inline. Verification itself uploads files."""
    if patch is None:
        return "(no file changes)"
    validate_patch(patch)
    parts = [f"<<<FILE {p}>>>\n{c}<<<END FILE>>>" for p, c in sorted(patch.files.items())]
    parts += [f"<<<DELETE {p}>>>" for p in patch.deletes]
    return "\n".join(parts) or "(no file changes)"


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


def _prefixes(reported_dir: str | None) -> list[str]:
    """Candidate workspace-relative locations of the harness directory."""
    out = [harness.HARNESS_DIR]
    if reported_dir:
        parts = [p for p in Path(reported_dir).parts if p not in ("/", "")]
        for i in range(len(parts)):
            out.append("/".join(parts[i:]))
    seen, uniq = set(), []
    for p in out:
        if p and p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def _download(env_id: str, path: str) -> bytes | None:
    try:
        return gemini.download_file(env_id, path)
    except Exception:  # noqa: BLE001 - a missing file is an observation, not a crash
        return None


def collect(env_id: str, reported_dir: str | None, attempts: int = 3) -> tuple[dict, dict, str]:
    """Download every artifact plus the harness inputs back from the sandbox snapshot.

    Retries (the snapshot can lag the interaction) only when the agent reported running the
    harness; otherwise one pass is enough to show nothing is there.
    """
    attempts = attempts if reported_dir else 1
    for attempt in range(attempts):
        for prefix in _prefixes(reported_dir):
            if _download(env_id, f"{prefix}/out/DONE") is not None:
                art = {}
                for name in harness.ARTIFACTS:
                    data = _download(env_id, f"{prefix}/out/{name}")
                    if data is not None:
                        art[name] = data
                returned = {
                    n: _download(env_id, f"{prefix}/{n}")
                    for n in ("verify.sh", "patch.tar.gz", "deletes.txt")
                }
                return art, returned, prefix
        if attempt + 1 < attempts:
            time.sleep(5 * (attempt + 1))
    return {}, {}, ""


def verify(
    repo_url: str,
    django_version: str,
    patch: Patch | None,
    test_command: str = "python manage.py test",
    previous_interaction_id: str | None = None,
    environment_id: str | None = None,
    source_commit: str = "",
    artifact_dir: Path | None = None,
) -> tuple[VerifyReport, gemini.Result]:
    from ..repository import validate_django_version, validate_source

    validate_source(repo_url, source_commit)
    validate_django_version(django_version)
    if patch is not None:
        validate_patch(patch)
    case = harness.SecurityCase.from_env()
    bundle = harness.build(repo_url, source_commit, django_version, patch, case)

    # Always a fresh sandbox: every verification starts from the source commit.
    res = gemini.run_agent(
        load("verify_harness", harness_dir=harness.HARNESS_DIR), sources=bundle.sources
    )
    reported_dir = None
    try:
        reported_dir = extract_json(res.text).get("harness_dir")
    except ValueError:
        pass
    art, returned, prefix = (
        collect(res.environment_id, reported_dir) if res.environment_id else ({}, {}, "")
    )

    report = harness.report_from_artifacts(
        art,
        bundle=bundle,
        returned={k: v for k, v in returned.items() if v is not None},
        commit=source_commit,
        django_version=django_version,
        case=case,
    )
    if not art:
        report.notes = "No artifacts could be retrieved from the sandbox. " + report.notes
    if case is None:
        report.notes += " No frozen security probe configured (JATAYU_PROBE_SHA256)."
    report.source_commit = source_commit
    report.patch_sha256 = patch_digest(patch or Patch())

    from ..config import settings

    directory = artifact_dir or settings().runs_dir / "artifacts" / (res.id or "unknown")[-24:]
    harness.save(art, directory)
    # Keep exactly what came back, plus what we expected, so the integrity check is auditable.
    harness.save({f"returned/{k}": v for k, v in returned.items() if v is not None}, directory)
    (directory / "expected.json").write_text(
        json.dumps(
            {
                "verify.sh": bundle.script_sha256,
                "patch.tar.gz": bundle.patch_sha256,
                "deletes.txt": hashlib.sha256(bundle.deletes.encode()).hexdigest(),
                "source_commit": source_commit,
                "django_version": django_version,
                "probe_sha256": case.sha256 if case else None,
                "interaction_id": res.id,
                "environment_id": res.environment_id,
            },
            indent=1,
        )
    )
    (directory / "harness.sh").write_text(bundle.script)
    (directory / "agent-reply.txt").write_text(res.text or "")
    (directory / "location.txt").write_text(f"{res.environment_id}\n{prefix}\n")
    return report, res
