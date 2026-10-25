# ruff: noqa: E501  (embedded shell script)
"""Sandbox harness for ANY ecosystem, driven by a user-approved execution recipe.

Same trust design as the Django harness (verify/harness.py), plus a worktree boundary:
- Every command from the recipe is mounted as its own file and run only inside the
  managed sandbox, never on the host. Inputs come back byte-for-byte or nothing counts.
- Before install and after the tests, the script hashes every non-ignored file in the
  worktree. The controller compares the "before" manifest with the tree it expects
  (source commit + patch) and checks that no expected file changed during the run.
- The JUnit report is copied from `junit_path` only if it is a regular file (not a
  symlink) inside the worktree and under the size limit.
- Security is NOT assessed here: generic runs are test verification only.
"""

from __future__ import annotations

import base64
import hashlib
import io
import re
import tarfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Protocol

from ..artifacts.parse import ArtifactError, parse_junit
from ..models import Failure, SuiteCounts, VerifyReport
from ..parse import Patch, check_path
from .harness import junit_failures

HARNESS_DIR = "jatayu"
MAX_REPORT_BYTES = 8_000_000
COMMANDS = ("install", "test", "version", "runtime", "check")
ARTIFACTS = [
    "DONE",
    "head.txt",
    "tree.before",
    "tree.after",
    "locks.txt",
    "runtime.txt",
    "version.txt",
    "version.exit",
    "install.exit",
    "install.log",
    "tests.exit",
    "tests.stdout",
    "tests.stderr",
    "junit.xml",
    "junit.status",
    "check.exit",
    "check.stdout",
    "check.stderr",
]
_COMMIT = re.compile(r"[0-9a-f]{40}")
_URL = re.compile(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?")
_VERSION = re.compile(r"[0-9A-Za-z][0-9A-Za-z.+-]{0,63}")


class Spec(Protocol):
    """The fields of unpinned.execution.ExecutionSpec this module relies on."""

    framework: str
    language: str
    source_version: str
    target_version: str
    install_command: str
    test_command: str
    version_command: str
    runtime_command: str
    junit_path: str
    notes_urls: list[str]
    check_command: str | None
    working_directory: str
    timeout_seconds: int

    def render(self, command: str, version: str) -> str: ...


def safe_relative(path: str, what: str) -> str:
    p = (path or ".").strip()
    if p in (".", "./"):
        return "."
    norm = check_path(p)
    if PurePosixPath(norm).is_absolute() or ".." in PurePosixPath(norm).parts:
        raise ValueError(f"{what} must be a relative path inside the repository")
    return norm


@dataclass
class Bundle:
    script: str
    patch_tgz: bytes
    deletes: str
    commands: dict[str, str]
    expected_version: str
    sources: list[dict] = field(default_factory=list)

    def digests(self) -> dict[str, str]:
        out = {
            "verify.sh": hashlib.sha256(self.script.encode()).hexdigest(),
            "patch.tar.gz": hashlib.sha256(self.patch_tgz).hexdigest(),
            "deletes.txt": hashlib.sha256(self.deletes.encode()).hexdigest(),
        }
        for name, cmd in self.commands.items():
            out[f"cmd/{name}.sh"] = hashlib.sha256(cmd.encode()).hexdigest()
        return out

    def expected_inputs(self) -> dict[str, bytes]:
        out = {
            "verify.sh": self.script.encode(),
            "patch.tar.gz": self.patch_tgz,
            "deletes.txt": self.deletes.encode(),
        }
        out.update({f"cmd/{n}.sh": c.encode() for n, c in self.commands.items()})
        return out


def _archive(patch: Patch | None) -> tuple[bytes, str]:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.PAX_FORMAT) as tar:
        for path, content in sorted((patch.files if patch else {}).items()):
            data = content.encode()
            info = tarfile.TarInfo(check_path(path))
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            tar.addfile(info, io.BytesIO(data))
    deletes = [check_path(p) for p in sorted(patch.deletes)] if patch else []
    return buf.getvalue(), "".join(f"{p}\n" for p in deletes)


def _inline(target: str, data: bytes) -> dict:
    return {
        "type": "inline",
        "target": target,
        "encoding": "base64",
        "content": base64.b64encode(data).decode(),
    }


def build(repo_url: str, commit: str, spec: Spec, version: str, patch: Patch | None) -> Bundle:
    if not _URL.fullmatch(repo_url):
        raise ValueError("repo_url must be https://github.com/owner/repo")
    if not _COMMIT.fullmatch(commit):
        raise ValueError("source commit must be a 40-character SHA")
    if not _VERSION.fullmatch(version):
        raise ValueError("version must be an exact version string")
    workdir = safe_relative(spec.working_directory, "working_directory")
    junit = safe_relative(spec.junit_path, "junit_path")
    timeout = int(spec.timeout_seconds)
    if not 30 <= timeout <= 3600:
        raise ValueError("timeout_seconds must be between 30 and 3600")
    commands = {
        "install": spec.render(spec.install_command, version),
        "test": spec.render(spec.test_command, version),
        "version": spec.render(spec.version_command, version),
        "runtime": spec.render(spec.runtime_command, version),
    }
    if spec.check_command:
        commands["check"] = spec.render(spec.check_command, version)
    for name, cmd in commands.items():
        if not cmd.strip():
            raise ValueError(f"{name} command is empty")
    tgz, deletes = _archive(patch)
    script = _SCRIPT.format(
        repo_url=repo_url.rstrip("/"),
        commit=commit,
        workdir=workdir,
        junit=junit,
        timeout=timeout,
        max_bytes=MAX_REPORT_BYTES,
    )
    b = Bundle(script, tgz, deletes, commands, version)
    b.sources = [
        _inline(f"{HARNESS_DIR}/{name}", data) for name, data in b.expected_inputs().items()
    ]
    return b


_SCRIPT = r"""#!/usr/bin/env bash
# Jatayu generic verification harness (controller-owned; do not edit).
set -u
HERE="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
OUT="$HERE/out"; W="$HERE/work"
rm -rf "$OUT" "$W"; mkdir -p "$OUT" "$W"
rec() {{ echo "$2" > "$OUT/$1"; }}
manifest() {{
  ( cd "$W/repo" && git ls-files -co --exclude-standard -z | sort -z | \
    while IFS= read -r -d '' f; do
      if [ -f "$f" ] && [ ! -L "$f" ]; then printf '%s  %s\n' "$(sha256sum -- "$f" | cut -d' ' -f1)" "$f"; fi
    done )
}}

git clone --quiet --no-checkout "{repo_url}" "$W/repo" > "$OUT/clone.log" 2>&1 || {{ echo done > "$OUT/DONE"; exit 0; }}
cd "$W/repo"
git fetch --quiet --depth 1 origin "{commit}" >> "$OUT/clone.log" 2>&1 || true
git checkout --quiet --detach "{commit}" >> "$OUT/clone.log" 2>&1
git rev-parse HEAD > "$OUT/head.txt"
tar xzf "$HERE/patch.tar.gz" --no-same-owner -C "$W/repo" >> "$OUT/clone.log" 2>&1
while IFS= read -r p; do [ -n "$p" ] && rm -f -- "$W/repo/$p"; done < "$HERE/deletes.txt"
manifest > "$OUT/tree.before"

cd "$W/repo/{workdir}" || {{ echo done > "$OUT/DONE"; exit 0; }}
timeout 900 bash "$HERE/cmd/runtime.sh" > "$OUT/runtime.txt" 2>&1
timeout 1800 bash "$HERE/cmd/install.sh" > "$OUT/install.log" 2>&1
rec install.exit $?
timeout 120 bash "$HERE/cmd/version.sh" > "$OUT/version.txt" 2>> "$OUT/install.log"
rec version.exit $?
for f in package-lock.json npm-shrinkwrap.json yarn.lock pnpm-lock.yaml poetry.lock uv.lock Pipfile.lock Gemfile.lock go.sum; do
  [ -f "$f" ] && sha256sum -- "$f" >> "$OUT/locks.txt"
done
touch "$OUT/locks.txt"

rm -f -- "{junit}"
timeout {timeout} bash "$HERE/cmd/test.sh" > "$OUT/tests.stdout" 2> "$OUT/tests.stderr"
rec tests.exit $?
ROOT="$(realpath -e "$W/repo")"
if [ -L "{junit}" ]; then rec junit.status symlink
elif [ ! -f "{junit}" ]; then rec junit.status missing
else
  REAL="$(realpath -e -- "{junit}")"
  SIZE="$(stat -c %s -- "{junit}")"
  case "$REAL" in "$ROOT"/*) ;; *) rec junit.status outside; REAL="";; esac
  if [ -n "$REAL" ] && [ "$SIZE" -le {max_bytes} ]; then cp -- "$REAL" "$OUT/junit.xml"; rec junit.status ok
  elif [ -n "$REAL" ]; then rec junit.status too_large; fi
fi
if [ -f "$HERE/cmd/check.sh" ]; then
  timeout 600 bash "$HERE/cmd/check.sh" > "$OUT/check.stdout" 2> "$OUT/check.stderr"
  rec check.exit $?
fi
manifest > "$OUT/tree.after"
echo done > "$OUT/DONE"
"""


# --- expected tree ---------------------------------------------------------------------------


def expected_manifest(tracked: dict[str, bytes], patch: Patch | None) -> dict[str, str]:
    """sha256 per path for the tree the tests must run on: source commit + patch."""
    out = {p: hashlib.sha256(b).hexdigest() for p, b in tracked.items()}
    if patch:
        for p in patch.deletes:
            out.pop(p, None)
        for p, content in patch.files.items():
            out[p] = hashlib.sha256(content.encode()).hexdigest()
    return out


def parse_manifest(raw: bytes | None) -> dict[str, str] | None:
    if raw is None:
        return None
    out = {}
    for line in raw.decode("utf-8", "replace").splitlines():
        if not line.strip():
            continue
        digest, _, path = line.partition("  ")
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or not path:
            return None
        out[path] = digest
    return out


def tree_problems(art: dict[str, bytes], expected: dict[str, str]) -> list[str]:
    before = parse_manifest(art.get("tree.before"))
    after = parse_manifest(art.get("tree.after"))
    if before is None or after is None:
        return ["worktree manifest missing or malformed"]
    problems = []
    if before != expected:
        missing = sorted(set(expected) - set(before))[:5]
        extra = sorted(set(before) - set(expected))[:5]
        changed = sorted(p for p in set(expected) & set(before) if expected[p] != before[p])[:5]
        problems.append(
            f"worktree before tests differs from source commit + patch "
            f"(missing {missing}, extra {extra}, changed {changed})"
        )
    modified = sorted(p for p in expected if p in after and after[p] != expected[p])
    removed = sorted(p for p in expected if p not in after)
    if modified or removed:
        problems.append(f"files changed during the run: {(modified + removed)[:5]}")
    return problems


# --- report ----------------------------------------------------------------------------------


def _txt(art: dict[str, bytes], name: str) -> str | None:
    raw = art.get(name)
    return None if raw is None else raw.decode("utf-8", "replace").strip()


def _int(art: dict[str, bytes], name: str) -> int | None:
    v = _txt(art, name)
    return int(v) if v is not None and re.fullmatch(r"-?[0-9]+", v) else None


def _tail(text: str | None, n: int = 15) -> str:
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    return "\n".join(lines[-n:])


def first_version(text: str | None) -> str | None:
    for line in (text or "").splitlines():
        line = line.strip().lstrip("vV")
        if line:
            return line
    return None


def report_from_artifacts(
    art: dict[str, bytes],
    *,
    bundle: Bundle,
    returned: dict[str, bytes],
    commit: str,
    expected_tree: dict[str, str],
    spec: Spec,
) -> VerifyReport:
    problems: list[str] = []
    if "DONE" not in art:
        problems.append("harness did not finish")
    for name, data in bundle.expected_inputs().items():
        if returned.get(name) != data:
            problems.append(f"{name} in sandbox differs from the one uploaded")
    head = _txt(art, "head.txt")
    if head != commit:
        problems.append(f"checked-out commit {head!r} is not the source commit")
    tree = tree_problems(art, expected_tree)
    problems += tree

    version = first_version(_txt(art, "version.txt"))
    if _int(art, "version.exit") != 0 or version != bundle.expected_version:
        problems.append(f"{spec.framework} version {version!r} is not {bundle.expected_version}")
    install_exit = _int(art, "install.exit")
    tests_exit = _int(art, "tests.exit")
    if tests_exit is None:
        problems.append("test exit status missing")
    elif tests_exit == 124:
        problems.append("tests timed out")
    status = _txt(art, "junit.status")

    failures: list[Failure] = []
    if status == "ok" and art.get("junit.xml") is not None:
        try:
            suite = parse_junit(art["junit.xml"])
            failures = junit_failures(art["junit.xml"])
        except ArtifactError as e:
            problems.append(f"JUnit rejected: {e}")
            suite = SuiteCounts(errors=1)
    else:
        suite = SuiteCounts(errors=1)
        if status in ("symlink", "outside", "too_large"):
            problems.append(f"JUnit report rejected: {status}")
        elif tests_exit == 0:
            problems.append("tests exited 0 without a JUnit report")
        failures = [
            Failure(test="test run produced no report", trace_head=_tail(_txt(art, "tests.stderr")))
        ]

    checks_exit = _int(art, "check.exit") if "check" in bundle.commands else None
    check = []
    if "check" in bundle.commands and checks_exit != 0:
        check = [
            ln
            for ln in _tail(_txt(art, "check.stderr") or _txt(art, "check.stdout"), 10).splitlines()
        ] or [f"check command exited {checks_exit}"]

    report = VerifyReport(
        python_version="",
        django_version="",
        test_command=bundle.commands["test"],
        suite=suite,
        failures=failures,
        check=check,
        exploits=[],
        install_ok=install_exit == 0,
        tests_exit_code=tests_exit,
        checks_exit_code=checks_exit,
        notes="; ".join(problems)
        or "Built from raw sandbox files retrieved via the Files API. Security not assessed.",
        framework=spec.framework,
        framework_version=version,
        runtime_version=first_version(_txt(art, "runtime.txt")),
        security_assessed=False,
        tree_verified=not tree and "DONE" in art,
    )
    report.artifacts_verified = not problems
    report.evidence_source = "sandbox_artifacts" if not problems else "agent_summary"
    return report


def is_green(r: VerifyReport, baseline: VerifyReport | None, *, require_check: bool) -> list[str]:
    """Test-verification blockers (empty = green). Never a security verdict."""
    out = []
    if not r.artifacts_verified or r.evidence_source != "sandbox_artifacts":
        out.append("evidence is not independently verified sandbox artifacts")
    if not r.tree_verified:
        out.append("worktree boundary not verified")
    if not r.install_ok:
        out.append("install failed")
    if r.tests_exit_code != 0:
        out.append(f"test command exited {r.tests_exit_code}")
    if r.suite.total <= 0:
        out.append("no tests collected")
    if r.suite.failed or r.suite.errors:
        out.append(f"{r.suite.failed} failed, {r.suite.errors} errors")
    if require_check and (r.checks_exit_code != 0 or r.check):
        out.append("required check failed")
    if baseline is not None:
        if r.suite.total < baseline.suite.total:
            out.append(f"suite shrank: {r.suite.total} vs {baseline.suite.total} at baseline")
        if r.suite.skipped > baseline.suite.skipped:
            out.append(
                f"more skipped tests than baseline ({r.suite.skipped} > {baseline.suite.skipped})"
            )
    return out


def save(art: dict[str, bytes], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, data in art.items():
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
