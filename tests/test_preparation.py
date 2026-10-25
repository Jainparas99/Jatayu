import hashlib
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from unpinned import cli
from unpinned.config import settings
from unpinned.models import SuiteCounts, VerifyReport
from unpinned.pack import Bundle
from unpinned.preparation import bump_only, recipe, resolve_adapter

URL = "https://github.com/acme/app"
COMMIT = "a" * 40


def generic_options():
    return {
        "source_version": "2.10.0",
        "target_version": "3.2.0",
        "framework": "ruby-jwt",
        "language": "Ruby",
        "test_command": "bundle exec rspec",
        "install_command": "bundle install",
        "notes_urls": ["https://example.com/upgrade"],
    }


@pytest.mark.parametrize("key", list(generic_options()))
def test_generic_requires_every_execution_input(key):
    options = generic_options()
    options.pop(key)
    with pytest.raises(ValueError, match="generic preparation requires"):
        resolve_adapter("generic", **options)


def test_generic_does_not_inherit_python_commands(tmp_path):
    adapter, source, target = resolve_adapter("generic", **generic_options())
    b = Bundle(root=tmp_path, files={"connector.rb": "puts :ok\n", "Gemfile": "gem 'jwt'\n"})
    value = recipe(adapter, b, URL, COMMIT, source, target)
    assert value["install_command"] == "bundle install"
    assert value["test_command"] == "bundle exec rspec"
    assert value["check_command"] is None
    assert value["baseline_command"] is None
    assert value["requested_target_version"] == "3.2.0"
    assert value["artifacts_verified"] is value["ready_for_review"] is False
    assert value["source_commit"] == COMMIT
    assert value["scope"] == "local_input_preparation"


def test_django_recipe_uses_selected_target_and_all_notes(tmp_path):
    adapter, source, target = resolve_adapter("django", target_version="5.2.18")
    value = recipe(adapter, Bundle(tmp_path, {"manage.py": "# app\n"}), URL, COMMIT, source, target)
    assert "Django==5.2.18" in value["install_command"]
    assert value["baseline_command"].endswith("--target-version 5.2")
    assert len(value["notes_urls"]) == 3


@pytest.mark.parametrize(
    "changes",
    [
        {"target_version": "2.10.0"},
        {"target_version": "3.2.0; echo bad"},
        {"source_version": "2.10.0\nignored"},
    ],
)
def test_rejects_invalid_or_identical_versions(changes):
    with pytest.raises(ValueError):
        resolve_adapter("generic", **(generic_options() | changes))


def test_generic_url_validation_and_omitted_inputs(tmp_path):
    options = generic_options() | {"notes_urls": ["https://user:password@example.com/notes"]}
    adapter, source, target = resolve_adapter("generic", **options)
    b = Bundle(tmp_path, {"x.rb": "ok"})
    with pytest.raises(ValueError, match="embedded credentials"):
        recipe(adapter, b, URL, COMMIT, source, target)
    adapter, source, target = resolve_adapter("generic", **generic_options())
    with pytest.raises(ValueError, match="omitted"):
        recipe(adapter, replace(b, skipped=["large.rb"]), URL, COMMIT, source, target)
    with pytest.raises(ValueError, match="immutable"):
        recipe(adapter, b, URL, "main", source, target)


def test_b0_uses_adapter_manifest_support_and_rejects_noop(tmp_path):
    adapter, _, _ = resolve_adapter("django")
    bundle = Bundle(tmp_path, {"pyproject.toml": 'dependencies = ["Django>=4.2,<5"]\n'})
    patch = bump_only(bundle, "5.2.18", adapter)
    assert patch.files == {"pyproject.toml": 'dependencies = ["Django==5.2.18"]\n'}
    with pytest.raises(ValueError, match="no dependency changes"):
        bump_only(Bundle(tmp_path, {"app.py": "import django"}), "5.2.18", adapter)


def configure_input(tmp_path, monkeypatch, contents):
    root = tmp_path / "input"
    root.mkdir()
    for name, content in contents.items():
        (root / name).write_text(content)
    monkeypatch.setattr(cli, "_clone", lambda url: root)
    monkeypatch.setattr(cli.subprocess, "check_output", lambda *a, **k: COMMIT)
    configured = replace(settings(), runs_dir=tmp_path / "runs")
    monkeypatch.setattr("unpinned.runs.settings", lambda: configured)
    return configured


def test_prepare_generic_persists_inventory_without_model_calls(tmp_path, monkeypatch):
    configured = configure_input(tmp_path, monkeypatch, {"connector.rb": "puts :ok\n"})
    monkeypatch.setattr("unpinned.gemini.ask", lambda *a, **k: pytest.fail("model called"))
    monkeypatch.setattr("unpinned.gemini.run_agent", lambda *a, **k: pytest.fail("agent called"))
    result = CliRunner().invoke(
        cli.app,
        [
            "prepare",
            URL,
            "--adapter",
            "generic",
            "--from-version",
            "2.10.0",
            "--target",
            "3.2.0",
            "--framework",
            "ruby-jwt",
            "--language",
            "Ruby",
            "--test-cmd",
            "bundle exec rspec",
            "--install-cmd",
            "bundle install",
            "--notes-url",
            "https://example.com/upgrade",
        ],
    )
    assert result.exit_code == 0, result.output
    files = list(configured.runs_dir.glob("*/input.json"))
    assert len(files) == 1
    value = json.loads(files[0].read_text())
    assert value["files"] == ["connector.rb"]
    assert not value["artifacts_verified"]
    assert not list(configured.runs_dir.glob("*/summary.json"))


def test_generic_run_blocks_before_clone_or_paid_calls(monkeypatch):
    monkeypatch.setattr(cli, "_clone", lambda *a: pytest.fail("cloned before validation"))
    result = CliRunner().invoke(cli.app, ["run", URL, "--adapter", "generic"])
    assert result.exit_code == 2
    assert "not implemented" in result.output


def test_untrusted_baseline_stops_before_migration(tmp_path, monkeypatch):
    configured = configure_input(tmp_path, monkeypatch, {"manage.py": "# app\n"})
    monkeypatch.setattr(
        "unpinned.verify.agent.verify",
        lambda *a, **k: (
            VerifyReport(install_ok=True, suite=SuiteCounts(passed=1)),
            SimpleNamespace(text="untrusted process summary"),
        ),
    )
    monkeypatch.setattr("unpinned.notes.notes_for", lambda *a: pytest.fail("continued past gate"))
    result = CliRunner().invoke(cli.app, ["run", URL, "--live"])
    assert result.exit_code == 2, result.output
    summaries = list(configured.runs_dir.glob("*/summary.json"))
    assert len(summaries) == 1
    assert json.loads(summaries[0].read_text())["review_blockers"]


def test_notes_for_uses_url_cache_without_network(tmp_path, monkeypatch):
    from unpinned.notes import notes_for

    adapter, source, target = resolve_adapter("generic", **generic_options())
    url = generic_options()["notes_urls"][0]
    (tmp_path / f"notes-{hashlib.sha256(url.encode()).hexdigest()[:16]}.txt").write_text(
        "Cached rules"
    )
    monkeypatch.setattr(
        "unpinned.notes.settings", lambda: replace(settings(), context_dir=tmp_path)
    )
    monkeypatch.setattr("unpinned.notes.httpx.get", lambda *a, **k: pytest.fail("network called"))
    assert "Cached rules" in notes_for(adapter, source, target)
