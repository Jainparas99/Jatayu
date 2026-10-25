"""Typer CLI: ping, spike, run, baseline, report, replay, serve."""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .config import ARGON, settings

app = typer.Typer(no_args_is_help=True, add_completion=False, pretty_exceptions_show_locals=False)
con = Console()


def _clone(repo_url: str) -> Path:
    from .repository import validate_source

    validate_source(repo_url)
    d = Path(tempfile.mkdtemp(prefix="jatayu-"))
    subprocess.run(
        ["git", "clone", "--depth", "1", "--", repo_url, str(d / "repo")], check=True, timeout=120
    )
    return d / "repo"


@app.command()
def ping() -> None:
    """One gemini-4-argon call: proves the key and SDK work."""
    from . import gemini

    t0 = time.monotonic()
    r = gemini.ask("Reply with the single word: pong", thinking_level="low")
    con.print(f"[green]{ARGON}[/] → {r.text!r} in {time.monotonic() - t0:.1f}s (id {r.id})")


@app.command()
def spike(
    repo_url: str, django: str = typer.Option(None, help="defaults to baseline 4.2.x")
) -> None:
    """Kickoff spike: does the repo install + run tests in the Antigravity sandbox?"""
    from .verify.agent import spike as do_spike

    t0 = time.monotonic()
    result = do_spike(repo_url, django or settings().baseline_django)
    result["_wall_seconds"] = round(time.monotonic() - t0, 1)
    con.print_json(json.dumps(result))


@app.command()
def prepare(
    repo_url: str,
    adapter: str = typer.Option("django", help="django | generic"),
    source_version: str | None = typer.Option(None, "--from-version"),
    target: str | None = typer.Option(None),
    framework: str | None = typer.Option(None),
    language: str | None = typer.Option(None),
    test_cmd: str | None = typer.Option(None),
    install_cmd: str | None = typer.Option(None),
    check_cmd: str | None = typer.Option(None),
    notes_url: list[str] | None = typer.Option(None, help="repeat for each upgrade-notes URL"),
) -> None:
    """Pin and inventory an input; save its recipe without running code or calling models."""
    from .pack import pack
    from .preparation import recipe, resolve_adapter, save_recipe

    try:
        selected, source, destination = resolve_adapter(
            adapter,
            source_version=source_version,
            target_version=target,
            framework=framework,
            language=language,
            test_command=test_cmd,
            install_command=install_cmd,
            check_command=check_cmd,
            notes_urls=notes_url,
        )
        root = _clone(repo_url)
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        value = recipe(
            selected, pack(root, adapter=selected), repo_url, commit, source, destination
        )
        directory = save_recipe(value)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    con.print(f"Prepared input: {directory / 'input.json'}")
    con.print("Commands have not been run. This is not verified migration evidence.")


@app.command()
def run(
    repo_url: str,
    target: str | None = typer.Option(
        None, help="exact target Django version; defaults to settings"
    ),
    live: bool = typer.Option(False, help="small repo, thinking medium, no PLAN step"),
    adapter: str = typer.Option("django", help="currently supported live adapter: django"),
) -> None:
    """Full pipeline: pack → plan → migrate → verify/fix loop. Ends at the Approve page."""
    from .loop import run_loop
    from .migrate import migrate
    from .models import RunSummary
    from .notes import notes_for
    from .pack import pack
    from .plan import make_plan
    from .preparation import recipe, resolve_adapter
    from .runs import new_run_id, run_dir, save_json, save_text
    from .verify.agent import verify

    s = settings()
    if adapter != "django":
        raise typer.BadParameter(
            "Generic remote verification is not implemented. "
            "Use `jatayu prepare --adapter generic` "
            "to inspect its input and execution recipe without calling a model."
        )
    try:
        selected, source, destination = resolve_adapter(adapter, target_version=target)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    summary = RunSummary(
        run_id=new_run_id("unpinned"),
        kind="unpinned",
        repo_url=repo_url,
        target_django=destination,
        started_at=datetime.now().isoformat(timespec="seconds"),
    )
    d = run_dir(summary.run_id)
    t0 = time.monotonic()
    root = _clone(repo_url)
    summary.source_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    bundle = pack(root, adapter=selected)
    save_json(
        d / "input.json",
        recipe(selected, bundle, repo_url, summary.source_commit, source, destination),
    )
    if bundle.skipped:
        raise ValueError(
            f"Input bundle omitted {len(bundle.skipped)} files; review before migration"
        )
    con.print(f"PACK  {len(bundle.files)} files, ~{bundle.approx_tokens:,} tokens")
    save_json(d / "bundle.json", {"sha256": bundle.sha256, "files": sorted(bundle.files)})
    summary.baseline_report, baseline_res = verify(
        repo_url,
        s.baseline_django,
        None,
        source_commit=summary.source_commit,
        artifact_dir=d / "artifacts" / "baseline",
    )
    con.print(
        f"BASELINE {s.baseline_django}: {summary.baseline_report.suite.passed} passed, "
        f"{summary.baseline_report.suite.failed} failed, {summary.baseline_report.suite.errors} "
        f"errors; evidence={summary.baseline_report.evidence_source}; "
        f"probe={[e.outcome for e in summary.baseline_report.exploits]}"
    )
    save_json(d / "baseline.json", summary.baseline_report)
    save_text(d / "baseline.raw.txt", baseline_res.text)
    if (
        not summary.baseline_report.install_ok
        or summary.baseline_report.suite.passed <= 0
        or summary.baseline_report.suite.failed
        or summary.baseline_report.suite.errors
        or not summary.baseline_report.artifacts_verified
        or summary.baseline_report.evidence_source != "sandbox_artifacts"
    ):
        summary.review_blockers = [
            "Baseline suite or independent sandbox evidence is incomplete; migration stopped."
        ]
        save_json(d / "summary.json", summary)
        raise typer.BadParameter(
            "A passing baseline with independently verified sandbox artifacts is required."
        )
    notes = notes_for(selected, source, destination)
    plan = None
    if not live:
        plan, pres = make_plan(
            bundle,
            notes,
            from_v=source,
            to_v=destination,
            framework=selected.framework,
            language=selected.language,
        )
        save_json(d / "plan.json", plan)
        con.print(f"PLAN  {len(plan.items)} breaking changes")
    patch, mres = migrate(
        bundle,
        notes,
        plan,
        from_v=source,
        to_v=destination,
        thinking_level="medium" if live else "high",
        framework=selected.framework,
        language=selected.language,
    )
    save_text(d / "migrate.raw.txt", mres.text)
    summary.input_tokens, summary.output_tokens = mres.input_tokens, mres.output_tokens
    con.print(
        f"MIGRATE {len(patch.files)} files, {len(patch.rejected)} rejected, "
        f"truncated={patch.truncated}"
    )
    summary, patch = run_loop(summary, patch, mres.id, bundle.files)
    summary.wall_seconds = time.monotonic() - t0
    save_json(d / "summary.json", summary)
    save_json(
        d / "patch.json", {"files": patch.files, "deletes": patch.deletes, "summary": patch.summary}
    )
    save_json(
        d / "originals.json",
        {p: bundle.files.get(p, "") for p in set(patch.files) | set(patch.deletes)},
    )
    status = "blocked" if summary.review_blockers else "ready for review"
    con.print(f"[bold]{status}[/] runs/{summary.run_id}")
    for blocker in summary.review_blockers:
        con.print(f"- {blocker}")
    if summary.review_blockers:
        raise typer.Exit(1)


@app.command()
def baseline(repo_url: str, mode: str = typer.Option("b0", help="b0 | b1 | b2")) -> None:
    from . import baselines
    from .pack import pack

    if mode not in {"b0", "b1", "b2"}:
        raise typer.BadParameter("mode must be b0, b1 or b2")
    bundle = pack(_clone(repo_url))
    summary = getattr(baselines, mode)(repo_url, bundle)
    con.print(f"saved runs/{summary.run_id}")


@app.command()
def report(run_ids: list[str] = typer.Argument(None)) -> None:
    """Before/after table from saved runs only."""
    from .report import load_runs, rows
    from .runs import run_path

    base = settings().runs_dir
    paths = (
        [run_path(r) / "summary.json" for r in run_ids]
        if run_ids
        else sorted(base.glob("*/summary.json"))
    )
    rs = rows(load_runs(paths))
    if not rs:
        con.print("No runs yet.")
        raise typer.Exit()
    t = Table(*rs[0].keys())
    for r in rs:
        t.add_row(*(str(v) for v in r.values()))
    con.print(t)


@app.command()
def replay(run_path: Path) -> None:
    """Print a saved run stage by stage (offline demo fallback). CP5: drive the UI too."""
    s = json.loads((run_path / "summary.json").read_text())
    for it in s["iterations"]:
        con.print(f"VERIFY {it['n']}: {it['report']['suite']}")
        time.sleep(0.8)


@app.command()
def prove_fixture(old_python: Path, new_python: Path) -> None:
    """Reproduce the owned security fixture locally; does not claim a cloud migration."""
    from .fixture import prove_fixture as prove

    result = prove(old_python, new_python)
    con.print_json(json.dumps(result))
    if not result["fixture_proven"]:
        raise typer.Exit(1)


@app.command()
def doctor() -> None:
    """Show local readiness without reading secret values into output or calling APIs."""
    from .config import ROOT

    s = settings()
    con.print(f"Project: {ROOT}")
    con.print(f"Gemini key configured: {bool(s.gemini_api_key)}")
    con.print(f"GitHub credential configured: {bool(s.github_token)}")
    con.print("Live sandbox execution: not yet verified")
    con.print("Independent sandbox artifact verifier: pending")
    con.print("PR publication: unavailable until verification and approval are implemented")
    git_root = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], cwd=ROOT, text=True
    ).strip()
    if Path(git_root).resolve() != ROOT:
        con.print("Git currently belongs to a parent folder. Do not stage from the parent.")


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    add_help_option=False,
)
def fleet(ctx: typer.Context) -> None:
    """Scan framework support dates. Use `jatayu fleet --help` for Fleet options."""
    from .fleet.__main__ import main

    raise typer.Exit(main(ctx.args))


@app.command()
def serve(port: int = 8000) -> None:
    import uvicorn

    uvicorn.run("unpinned.server:app", host="127.0.0.1", port=port, reload=False)


if __name__ == "__main__":
    app()
