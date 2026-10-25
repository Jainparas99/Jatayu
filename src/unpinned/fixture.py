"""Execute only the owned fixture with explicitly selected Python interpreters."""

import hashlib
import json
import subprocess
from pathlib import Path

from .config import ROOT
from .runs import new_run_id, run_dir, save_json, save_text


def prove_fixture(old_python: Path, new_python: Path) -> dict:
    probe = ROOT / "security_tests" / "probe_formset.py"
    digest = hashlib.sha256(probe.read_bytes()).hexdigest()
    directory = run_dir(new_run_id("local-fixture"))
    observations = {}
    for label, python, version in (
        ("before", old_python, "4.2.30"),
        ("after", new_python, "5.2.18"),
    ):
        process = subprocess.run(
            [str(python.absolute()), str(probe)], capture_output=True, text=True, timeout=30
        )
        save_text(directory / f"{label}.stdout.txt", process.stdout)
        save_text(directory / f"{label}.stderr.txt", process.stderr)
        if process.returncode:
            raise RuntimeError(f"{label} fixture failed; see {directory}")
        result = json.loads(process.stdout)
        if result["django_version"] != version or result["probe_sha256"] != digest:
            raise ValueError(f"{label} fixture version or hash does not match")
        observations[label] = result
    proven = (
        observations["before"]["outcome"] == "vulnerable"
        and observations["after"]["outcome"] == "blocked"
        and all(result["benign_control_passed"] for result in observations.values())
    )
    proof = {
        "evidence_source": "local_fixture",
        "fixture_proven": proven,
        "observations": observations,
    }
    save_json(directory / "proof.json", proof)
    return {**proof, "artifact_directory": str(directory)}
