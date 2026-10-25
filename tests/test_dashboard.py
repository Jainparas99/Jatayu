"""Runs/Fleet integration and honest evidence presentation; no provider or network calls."""

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from unpinned import api, cli
from unpinned.config import settings
from unpinned.models import Iteration, RunSummary, SuiteCounts, VerifyReport
from unpinned.parse import Patch, patch_digest
from unpinned.runs import save_json
from unpinned.server import app


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    import unpinned.runs

    configured = replace(
        settings(),
        runs_dir=tmp_path,
        gemini_api_key="secret-gemini-test-value",
        github_token="secret-github-test-value",
        fork_owner="private-test-owner",
    )
    monkeypatch.setattr(api, "settings", lambda: configured)
    monkeypatch.setattr(unpinned.runs, "settings", lambda: configured)
    monkeypatch.setenv("JATAYU_DASHBOARD_TOKEN", "secret-dashboard-test-value")
    return tmp_path, TestClient(app)


def saved(root, run_id="recorded", report=None, started="2026-10-25T13:30:00"):
    patch = Patch(files={"app.py": "after\n"})
    summary = RunSummary(
        run_id=run_id,
        kind="unpinned",
        repo_url="https://github.com/example/app",
        target_django="5.2.18",
        started_at=started,
        source_commit="a" * 40,
        iterations=[Iteration(n=1, report=report)] if report else [],
    )
    save_json(root / run_id / "summary.json", summary)
    save_json(root / run_id / "patch.json", {"files": patch.files, "deletes": patch.deletes})
    save_json(root / run_id / "originals.json", {"app.py": "before\n"})
    return patch


def test_config_returns_presence_not_values(workspace, monkeypatch):
    _, client = workspace
    response = client.get("/api/config")
    assert response.status_code == 200
    assert all(response.json()["credentials"].values())
    for secret in ("secret-gemini", "secret-github", "secret-dashboard", "private-test-owner"):
        assert secret not in response.text
        assert secret not in client.get("/api/overview").text
    monkeypatch.delenv("JATAYU_DASHBOARD_TOKEN")
    assert client.get("/api/config").json()["write_access"] == "read_only"
    assert not client.get("/api/config").json()["credentials"]["JATAYU_DASHBOARD_TOKEN"]


def test_empty_workspace_has_no_invented_runs(workspace):
    root, client = workspace
    save_json(root / "local_fixture" / "proof.json", {"fixture_proven": True})
    data = client.get("/api/overview").json()
    assert data["runs"] == []
    assert data["counts"] == dict(runs=0, ready_for_review=0, blocked=0, verified_artifacts=0)
    assert not data["configuration"]["browser_execution_available"]
    assert not data["configuration"]["publication_available"]


def test_inventory_is_newest_first_and_skips_invalid_artifacts(workspace):
    root, client = workspace
    saved(root, "older", started="2026-10-25T12:00:00")
    saved(root, "newer")
    save_json(root / "broken" / "summary.json", {"unusable": True})
    save_json(
        root / "mismatched" / "summary.json",
        RunSummary(
            run_id="elsewhere",
            kind="b0",
            repo_url="https://github.com/example/app",
            target_django="5.2.18",
            started_at="now",
        ),
    )
    (root / "escaping").symlink_to(root.parent)
    data = client.get("/api/overview").json()
    assert [r["run_id"] for r in data["runs"]] == ["newer", "older"]
    assert data["counts"]["blocked"] == 2
    assert data["counts"]["ready_for_review"] == 0
    assert all(r["blocker_count"] > 0 for r in data["runs"])


@pytest.mark.parametrize(
    "source,verified",
    [("agent_summary", True), ("local_fixture", True), ("sandbox_artifacts", False)],
)
def test_untrusted_claims_do_not_become_verified_metrics(workspace, source, verified):
    root, client = workspace
    saved(
        root,
        report=VerifyReport(
            suite=SuiteCounts(passed=9999),
            evidence_source=source,
            artifacts_verified=verified,
        ),
    )
    data = client.get("/api/overview").json()
    assert data["counts"]["verified_artifacts"] == 0
    assert data["counts"]["ready_for_review"] == 0
    assert "9999" not in str(data)


def test_review_returns_actual_diff_and_rechecks_changed_patch(workspace):
    root, client = workspace
    patch = saved(root)
    report = VerifyReport(patch_sha256=patch_digest(patch), source_commit="a" * 40)
    saved(root, report=report)
    first = client.get("/api/runs/recorded/review").json()
    assert first["patch_sha256"] == patch_digest(patch)
    assert "-before" in first["diff"] and "+after" in first["diff"]
    assert not first["publication_available"] and not first["ready_for_review"]
    save_json(root / "recorded" / "patch.json", {"files": {"app.py": "changed\n"}})
    second = client.get("/api/runs/recorded/review").json()
    assert second["patch_sha256"] != first["patch_sha256"]
    assert "Current patch differs from the verified patch." in second["blockers"]
    response = client.post(
        "/api/runs/recorded/approve",
        json={"patch_sha256": first["patch_sha256"]},
        headers={"Authorization": "Bearer secret-dashboard-test-value"},
    )
    assert response.status_code == 409


def test_runs_fleet_and_assets_share_server(workspace):
    _, client = workspace
    for path in ("/", "/fleet", "/static/app.js", "/static/app.css", "/healthz"):
        assert client.get(path).status_code == 200
    assert 'href="/fleet"' in client.get("/").text
    assert 'href="/"' in client.get("/fleet").text
    assert client.post("/api/runs/recorded/approve").status_code == 401
    assert client.post("/api/fleet/scan", json={"targets": ["/etc"]}).status_code == 401


def test_adapter_capabilities_are_explicit(workspace):
    _, client = workspace
    data = {a["name"]: a for a in client.get("/api/adapters").json()}
    assert data["django"]["status"] == "verification_pending"
    assert data["generic"]["status"] == "preparation_only"
    assert data["rails"]["status"] == "roadmap"
    assert data["spring-boot"]["status"] == "roadmap"


def test_fleet_cli_forwards_options_and_exit_status(monkeypatch):
    import unpinned.fleet.__main__

    received = []
    monkeypatch.setattr(unpinned.fleet.__main__, "main", lambda args: received.extend(args) or 1)
    result = CliRunner().invoke(cli.app, ["fleet", "scan", ".", "--fail-on", "eol"])
    assert received == ["scan", ".", "--fail-on", "eol"]
    assert result.exit_code == 1


def test_serve_uses_the_shared_protected_server(monkeypatch):
    import uvicorn

    received = []
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: received.append((args, kwargs)))
    cli.serve(8010)
    assert received == [(("unpinned.server:app",), dict(host="127.0.0.1", port=8010, reload=False))]
