from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

from unpinned import api, gemini
from unpinned.config import settings
from unpinned.models import RunSummary, SuiteCounts, VerifyReport
from unpinned.parse import Patch
from unpinned.runs import run_path, save_json
from unpinned.verify.agent import verify


def test_run_path_rejects_traversal_and_escaping_symlink(tmp_path):
    for bad in ("../private", ".", "", "/tmp", "a/b"):
        with pytest.raises(ValueError):
            run_path(bad, tmp_path)
    (tmp_path / "escape").symlink_to(tmp_path.parent)
    with pytest.raises(ValueError):
        run_path("escape", tmp_path)


def test_model_cannot_self_certify_sandbox_artifacts(monkeypatch):
    response = VerifyReport(
        artifacts_verified=True,
        evidence_source="sandbox_artifacts",
        install_ok=True,
        suite=SuiteCounts(passed=8),
    )
    monkeypatch.setattr(
        gemini,
        "run_agent",
        lambda *a, **k: NS(text=response.model_dump_json(), id="i", environment_id="env"),
    )
    report, _ = verify("https://github.com/example/app", "5.2.18", Patch(), source_commit="a" * 40)
    assert not report.artifacts_verified
    assert report.evidence_source == "agent_summary"


def test_artifact_symlink_cannot_read_outside_run(tmp_path, monkeypatch):
    import unpinned.runs

    configured = replace(settings(), runs_dir=tmp_path)
    monkeypatch.setattr(unpinned.runs, "settings", lambda: configured)
    (tmp_path / "r").mkdir()
    outside = tmp_path / "private.json"
    outside.write_text("private")
    (tmp_path / "r" / "summary.json").symlink_to(outside)
    with pytest.raises(ValueError, match="escapes"):
        unpinned.runs.run_file("r", "summary.json")


def test_incomplete_run_cannot_publish_even_with_click(tmp_path, monkeypatch):
    import unpinned.review
    import unpinned.runs

    configured = replace(settings(), runs_dir=tmp_path)
    monkeypatch.setattr(unpinned.runs, "settings", lambda: configured)
    monkeypatch.setattr(api, "settings", lambda: configured)
    save_json(
        tmp_path / "r" / "summary.json",
        RunSummary(
            run_id="r",
            kind="unpinned",
            repo_url="https://github.com/example/app",
            target_django="5.2.18",
            started_at="now",
        ),
    )
    monkeypatch.setenv("JATAYU_DASHBOARD_TOKEN", "review-test-token")
    client = TestClient(api.app, headers={"Authorization": "Bearer review-test-token"})
    review = client.get("/api/runs/r/review")
    assert review.status_code == 200
    assert not review.json()["ready_for_review"]
    assert client.post("/api/runs/r/approve", json={"patch_sha256": "a" * 64}).status_code == 409
    assert client.post("/api/runs/r/approve").status_code == 422


def test_patch_change_invalidates_saved_verification(tmp_path, monkeypatch):
    import unpinned.runs
    from unpinned.models import Iteration
    from unpinned.parse import patch_digest
    from unpinned.review import review_state

    configured = replace(settings(), runs_dir=tmp_path)
    monkeypatch.setattr(unpinned.runs, "settings", lambda: configured)
    original_patch = Patch(files={"app.py": "first\n"})
    report = VerifyReport(patch_sha256=patch_digest(original_patch))
    save_json(
        tmp_path / "r" / "summary.json",
        RunSummary(
            run_id="r",
            kind="unpinned",
            repo_url="https://github.com/example/app",
            target_django="5.2.18",
            started_at="now",
            iterations=[Iteration(n=1, report=report)],
        ),
    )
    save_json(tmp_path / "r" / "patch.json", {"files": {"app.py": "second\n"}})
    save_json(tmp_path / "r" / "originals.json", {"app.py": "before\n"})
    review = review_state("r")
    assert "Current patch differs from the verified patch." in review["blockers"]
    assert "+second" in review["diff"] and "-before" in review["diff"]


def test_settings_repr_does_not_expose_credentials():
    configured = replace(settings(), gemini_api_key="private-google", github_token="private-github")
    assert "private-google" not in repr(configured)
    assert "private-github" not in repr(configured)
