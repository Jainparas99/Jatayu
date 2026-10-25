from types import SimpleNamespace as NS

import pytest
from test_generic_harness import COMMIT, URL, Spec

from unpinned import gemini, generic_pipeline
from unpinned.models import SuiteCounts, VerifyReport


def test_untrusted_baseline_stops_before_any_model_call(tmp_path, monkeypatch):
    from dataclasses import replace

    import unpinned.runs
    from unpinned.config import settings

    cfg = replace(settings(), runs_dir=tmp_path)
    monkeypatch.setattr(unpinned.runs, "settings", lambda: cfg)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "index.js").write_text("x\n")
    monkeypatch.setattr(generic_pipeline, "checkout", lambda url, c: (repo, COMMIT))
    monkeypatch.setattr(generic_pipeline, "tracked_files", lambda root: {"index.js": b"x\n"})
    untrusted = VerifyReport(install_ok=True, suite=SuiteCounts(passed=3), tests_exit_code=0)
    monkeypatch.setattr(
        generic_pipeline,
        "sandbox_verify",
        lambda *a, **k: (untrusted, NS(id="i", environment_id="e")),
    )
    monkeypatch.setattr(gemini, "ask", lambda *a, **k: pytest.fail("model called"))
    with pytest.raises(generic_pipeline.GenericRunError, match="not a trusted passing suite"):
        generic_pipeline.run_generic(URL, spec=Spec())
    (summary,) = list(tmp_path.glob("*/summary.json"))
    text = summary.read_text()
    assert "Security not assessed" in text and '"tests_only"' in text


def test_generic_allowlist_adds_only_the_npm_registry():
    from unpinned.config import GENERIC_EXTRA_DOMAINS

    assert GENERIC_EXTRA_DOMAINS == ["registry.npmjs.org"]
