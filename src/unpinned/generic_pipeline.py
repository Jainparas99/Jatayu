# ruff: noqa: E501
"""Language-agnostic upgrade: any repository, driven by an execution recipe (ExecutionSpec).

Called by `jatayu run URL --adapter generic --recipe FILE`. Every command in the recipe runs
only inside the managed sandbox. Results come only from raw artifacts downloaded through the
Files API and checked against the expected worktree. Generic runs are TEST VERIFICATION
ONLY: security is never assessed here, so publication stays blocked.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path

from . import gemini
from .config import GENERIC_EXTRA_DOMAINS, SANDBOX_ALLOWLIST, settings
from .jsonx import extract_json
from .loop import merge
from .models import Iteration, RunSummary, VerifyReport
from .parse import Patch, parse, patch_digest, validate_patch
from .prompts import load
from .runs import new_run_id, run_dir, save_json, save_text
from .verify import generic_harness as gh
from .verify.agent import _download, _prefixes

SECURITY_BLOCKER = (
    "Security not assessed: generic runs are test verification only; "
    "security approval and publication stay blocked."
)


class GenericRunError(RuntimeError):
    """The run did not produce a trusted passing execution. The summary is saved anyway."""


def _spec_dict(spec) -> dict:
    if hasattr(spec, "model_dump"):
        return spec.model_dump(mode="json")
    if is_dataclass(spec):
        return asdict(spec)
    return dict(vars(spec))


def checkout(repo_url: str, commit: str | None) -> tuple[Path, str]:
    """Pin the exact commit locally (read-only use: hashing and packing, never executing)."""
    from .repository import validate_source

    validate_source(repo_url, commit)
    root = Path(tempfile.mkdtemp(prefix="jatayu-generic-")) / "repo"
    run = lambda *a: subprocess.run(a, check=True, capture_output=True, timeout=180)  # noqa: E731
    if commit:
        root.mkdir(parents=True)
        run("git", "-C", str(root), "init", "-q")
        run("git", "-C", str(root), "remote", "add", "origin", repo_url)
        run("git", "-C", str(root), "fetch", "-q", "--depth", "1", "origin", commit)
        run("git", "-C", str(root), "checkout", "-q", "--detach", "FETCH_HEAD")
    else:
        run("git", "clone", "-q", "--depth", "1", "--", repo_url, str(root))
    head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if commit and head != commit:
        raise GenericRunError(f"checked out {head}, expected {commit}")
    return root, head


def tracked_files(root: Path) -> dict[str, bytes]:
    names = subprocess.check_output(["git", "-C", str(root), "ls-files", "-z"]).split(b"\0")
    out = {}
    for raw in names:
        if not raw:
            continue
        rel = raw.decode()
        p = root / rel
        if p.is_file() and not p.is_symlink():
            out[rel] = p.read_bytes()
    return out


def sandbox_verify(
    repo_url: str,
    commit: str,
    spec,
    version: str,
    patch: Patch | None,
    tracked: dict[str, bytes],
    directory: Path,
) -> tuple[VerifyReport, gemini.Result]:
    bundle = gh.build(repo_url, commit, spec, version, patch)
    expected_tree = gh.expected_manifest(tracked, patch)
    res = gemini.run_agent(
        load("verify_harness", harness_dir=gh.HARNESS_DIR),
        sources=bundle.sources,
        allowlist=SANDBOX_ALLOWLIST + GENERIC_EXTRA_DOMAINS,
    )
    reported = None
    try:
        reported = extract_json(res.text).get("harness_dir")
    except ValueError:
        pass
    art: dict[str, bytes] = {}
    returned: dict[str, bytes] = {}
    for attempt in range(3 if reported else 1):
        for prefix in _prefixes(reported):
            if (
                res.environment_id
                and _download(res.environment_id, f"{prefix}/out/DONE") is not None
            ):
                for name in gh.ARTIFACTS:
                    data = _download(res.environment_id, f"{prefix}/out/{name}")
                    if data is not None:
                        art[name] = data
                for name in bundle.expected_inputs():
                    data = _download(res.environment_id, f"{prefix}/{name}")
                    if data is not None:
                        returned[name] = data
                break
        if art:
            break
        time.sleep(5 * (attempt + 1))
    report = gh.report_from_artifacts(
        art,
        bundle=bundle,
        returned=returned,
        commit=commit,
        expected_tree=expected_tree,
        spec=spec,
    )
    if not art:
        report.notes = "No artifacts could be retrieved from the sandbox. " + report.notes
    report.source_commit = commit
    report.patch_sha256 = patch_digest(patch or Patch())
    gh.save(art, directory)
    gh.save({f"returned/{k}": v for k, v in returned.items()}, directory)
    (directory / "expected.json").write_text(
        json.dumps(
            {
                "inputs": bundle.digests(),
                "tree": expected_tree,
                "source_commit": commit,
                "version": version,
                "interaction_id": res.id,
                "environment_id": res.environment_id,
            },
            indent=1,
        )
    )
    save_text(directory / "agent-reply.txt", res.text or "")
    return report, res


def _failures_text(r: VerifyReport, blockers: list[str]) -> str:
    lines = [f"blockers: {blockers}", f"suite: {r.suite.model_dump()}"]
    lines += [f"- {f.test}\n{f.trace_head}" for f in r.failures[:40]]
    lines += [f"- check: {c}" for c in r.check]
    return "\n".join(lines)


def run_generic(repo_url: str, *, spec, live: bool = False) -> RunSummary:
    from .adapters import get
    from .migrate import migrate
    from .notes import notes_for
    from .pack import pack
    from .plan import make_plan

    s = settings()
    commit_req = getattr(spec, "source_commit", None)
    adapter = get(
        "generic",
        framework=spec.framework,
        language=spec.language,
        test_command=spec.test_command,
        install_command=spec.install_command,
        check_command=spec.check_command,
        notes_urls=list(spec.notes_urls),
    )
    summary = RunSummary(
        run_id=new_run_id("unpinned"),
        kind="unpinned",
        repo_url=repo_url,
        target_django=spec.target_version,  # kept for schema compatibility
        started_at=datetime.now().isoformat(timespec="seconds"),
        framework=spec.framework,
        source_version=spec.source_version,
        scope="tests_only",
        review_blockers=[SECURITY_BLOCKER],
    )
    d = run_dir(summary.run_id)
    save_json(d / "execution_spec.json", _spec_dict(spec))
    t0 = time.monotonic()

    def fail(reason: str) -> None:
        summary.review_blockers = [reason, SECURITY_BLOCKER]
        summary.wall_seconds = time.monotonic() - t0
        save_json(d / "summary.json", summary)
        raise GenericRunError(reason)

    root, commit = checkout(repo_url, commit_req)
    summary.source_commit = commit
    tracked = tracked_files(root)
    bundle = pack(root, adapter=adapter)
    save_json(
        d / "bundle.json",
        {"sha256": bundle.sha256, "files": sorted(bundle.files), "skipped": bundle.skipped},
    )
    save_json(d / "summary.json", summary)
    print(f"PACK  {len(bundle.files)} files, ~{bundle.approx_tokens:,} tokens", flush=True)

    base, _ = sandbox_verify(
        repo_url, commit, spec, spec.source_version, None, tracked, d / "artifacts" / "baseline"
    )
    summary.baseline_report = base
    save_json(d / "baseline.json", base)
    save_json(d / "summary.json", summary)
    print(
        f"BASELINE {spec.framework} {base.framework_version}: {base.suite.passed} passed, "
        f"{base.suite.failed} failed, {base.suite.errors} errors, {base.suite.skipped} skipped; "
        f"evidence={base.evidence_source}; tree={base.tree_verified}",
        flush=True,
    )
    blockers = gh.is_green(base, None, require_check=bool(spec.check_command))
    if blockers:
        fail(f"Baseline is not a trusted passing suite: {blockers}; {base.notes}")

    notes = notes_for(adapter, spec.source_version, spec.target_version)
    plan = None
    if not live:
        plan, _ = make_plan(
            bundle,
            notes,
            from_v=spec.source_version,
            to_v=spec.target_version,
            framework=spec.framework,
            language=spec.language,
        )
        save_json(d / "plan.json", plan)
        print(f"PLAN  {len(plan.items)} breaking changes", flush=True)
    patch, mres = migrate(
        bundle,
        notes,
        plan,
        from_v=spec.source_version,
        to_v=spec.target_version,
        thinking_level="medium" if live else "high",
        framework=spec.framework,
        language=spec.language,
    )
    save_text(d / "migrate.raw.txt", mres.text)
    summary.input_tokens, summary.output_tokens = mres.input_tokens, mres.output_tokens
    print(
        f"MIGRATE {len(patch.files)} files, {len(patch.rejected)} rejected, "
        f"truncated={patch.truncated}",
        flush=True,
    )
    if patch.truncated or patch.rejected:
        save_json(
            d / "patch.rejected.json", {"rejected": patch.rejected, "truncated": patch.truncated}
        )
        fail(f"Migration patch rejected: {patch.rejected[:5]} truncated={patch.truncated}")
    validate_patch(patch)

    originals = {p: b.decode("utf-8", "replace") for p, b in tracked.items()}
    last_id = mres.id
    green: list[str] = ["not verified"]
    for n in range(1, s.max_iterations + 1):
        t1 = time.monotonic()
        report, res = sandbox_verify(
            repo_url,
            commit,
            spec,
            spec.target_version,
            patch,
            tracked,
            d / "artifacts" / f"verify-{n}",
        )
        green = gh.is_green(report, base, require_check=bool(spec.check_command))
        summary.iterations.append(
            Iteration(
                n=n,
                interaction_id=res.id,
                environment_id=res.environment_id,
                files_changed=len(patch.files) + len(patch.deletes),
                report=report,
                wall_seconds=time.monotonic() - t1,
            )
        )
        save_json(d / f"verify-{n}.json", report)
        save_json(
            d / "patch.json",
            {"files": patch.files, "deletes": patch.deletes, "summary": patch.summary},
        )
        save_json(
            d / "originals.json",
            {p: originals.get(p, "") for p in set(patch.files) | set(patch.deletes)},
        )
        summary.review_blockers = [*green, SECURITY_BLOCKER]
        save_json(d / "summary.json", summary)
        print(
            f"VERIFY {n}: {spec.framework} {report.framework_version}: {report.suite.passed} passed, "
            f"{report.suite.failed} failed, {report.suite.errors} errors; "
            f"evidence={report.evidence_source}; tree={report.tree_verified}",
            flush=True,
        )
        if not green or n == s.max_iterations or not report.artifacts_verified:
            break
        known = {**{q: "" for q in patch.files}, **originals}
        fres = gemini.ask(
            load(
                "fix_generic",
                framework=spec.framework,
                to_version=spec.target_version,
                failures=_failures_text(report, green),
            ),
            thinking_level="high",
            background=True,
            max_output_tokens=s.max_output_tokens,
            previous_interaction_id=last_id,
        )
        update = parse(fres.text, known_files=known)
        save_text(d / f"fix-{n}.raw.txt", fres.text)
        if update.truncated or update.rejected:
            fail(f"Repair patch rejected: {update.rejected[:5]} truncated={update.truncated}")
        last_id = fres.id
        patch = merge(patch, update)

    summary.wall_seconds = time.monotonic() - t0
    save_json(d / "summary.json", summary)
    if green:
        raise GenericRunError(
            f"Target suite not green after {len(summary.iterations)} attempts: {green}"
        )
    digest = hashlib.sha256(json.dumps(patch.files, sort_keys=True).encode()).hexdigest()
    print(
        f"TESTS VERIFIED (security not assessed) runs/{summary.run_id} patch {digest[:16]}",
        flush=True,
    )
    return summary
