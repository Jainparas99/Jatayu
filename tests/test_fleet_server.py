import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from unpinned.server import app  # noqa: E402

client = TestClient(app)


def test_reads_are_open_writes_need_token(monkeypatch):
    assert client.get("/healthz").json() == {"ok": True}
    monkeypatch.delenv("JATAYU_DASHBOARD_TOKEN", raising=False)
    r = client.post("/api/fleet/scan", json={"targets": ["https://github.com/a/b"]})
    assert r.status_code == 403  # read-only deployment
    monkeypatch.setenv("JATAYU_DASHBOARD_TOKEN", "s3cret")
    r = client.post("/api/fleet/scan", json={"targets": ["https://github.com/a/b"]})
    assert r.status_code == 401
    r = client.post(
        "/api/fleet/scan",
        json={"targets": ["/etc"]},
        headers={"Authorization": "Bearer s3cret"},
    )
    assert r.status_code == 422  # local paths are never accepted over HTTP


def test_approve_is_also_token_gated(monkeypatch):
    monkeypatch.delenv("JATAYU_DASHBOARD_TOKEN", raising=False)
    assert client.post("/api/runs/anything/approve").status_code == 403
