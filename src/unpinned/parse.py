"""Parser for Argon's long-decode FILE-block output, with path safety (SPEC §6)."""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

FILE_RE = re.compile(r"<<<FILE (?P<path>[^>\n]+)>>>\n(?P<body>.*?)\n?<<<END FILE>>>", re.S)
DELETE_RE = re.compile(r"<<<DELETE (?P<path>[^>\n]+)>>>")
SUMMARY_RE = re.compile(r"<<<SUMMARY>>>\n(?P<body>.*?)<<<END SUMMARY>>>", re.S)

FORBIDDEN_PREFIXES = (".git/", ".github/workflows/")
SECRET_NAMES = {".env", "secrets.py", "local_settings.py", "id_rsa", "credentials.json"}


class UnsafePath(ValueError):
    pass


@dataclass
class Patch:
    files: dict[str, str] = field(default_factory=dict)
    deletes: list[str] = field(default_factory=list)
    summary: dict[str, str] = field(default_factory=dict)
    rejected: list[tuple[str, str]] = field(default_factory=list)  # (path, reason)
    truncated: bool = False


def check_path(path: str) -> str:
    """Return a normalized relative path or raise UnsafePath."""
    p = path.strip()
    if not p or p.startswith("/") or "\\" in p or re.match(r"^[A-Za-z]:", p):
        raise UnsafePath("absolute or invalid path")
    parts = PurePosixPath(p).parts
    if not parts or any(ord(c) < 32 for c in p):
        raise UnsafePath("empty or control-character path")
    if ".." in parts:
        raise UnsafePath("path escapes repo")
    norm = PurePosixPath(*parts).as_posix()
    if (
        ".git" in parts
        or norm in (".git", ".github/workflows")
        or any(norm.startswith(f) for f in FORBIDDEN_PREFIXES)
    ):
        raise UnsafePath("protected path")
    if "security_tests" in parts:
        raise UnsafePath("independent security probes are protected")
    name = PurePosixPath(norm).name
    if name in SECRET_NAMES or name.startswith(".env"):
        raise UnsafePath("secrets file")
    return norm


_SKIP_MARKERS = re.compile(
    r"@(?:unittest\.)?skip|\.skipTest\(|expectedFailure|pytest\.mark\.(?:skip|xfail)"
    r"|\bskipIf\b|\bskipUnless\b"
)
_TEST_DEF = re.compile(r"^\s*(?:async\s+)?def\s+test", re.M)
_ASSERT = re.compile(r"\bassert", re.I)


def is_test_file(path: str) -> bool:
    pp = PurePosixPath(path)
    return (
        any(part.lower() in {"tests", "test"} for part in pp.parts[:-1])
        or pp.name.startswith("test_")
        or pp.name in {"tests.py", "conftest.py"}
    )


def weakening_reason(original: str | None, new: str | None) -> str | None:
    """Why an edit to a test file weakens the suite, or None if it doesn't.

    Upgrades legitimately edit tests (renamed assertion helpers, removed settings in
    override_settings). They may not drop tests, drop assertions, or add skips.
    """
    if new is None:
        return "deleting a test file is not allowed"
    before = original or ""
    if len(_TEST_DEF.findall(new)) < len(_TEST_DEF.findall(before)):
        return "removes test methods"
    if len(_SKIP_MARKERS.findall(new)) > len(_SKIP_MARKERS.findall(before)):
        return "adds skip or expected-failure markers"
    if len(_ASSERT.findall(new)) < len(_ASSERT.findall(before)):
        return "removes assertions"
    return None


def parse(output: str, known_files: set[str] | dict[str, str] | None = None) -> Patch:
    """Parse FILE/DELETE/SUMMARY blocks.

    known_files: paths in the input bundle. A FILE not in it is accepted only if the
    SUMMARY lists it (as a new file). When it is a dict of original contents, edits to
    test files are also checked so they cannot weaken the suite.
    """
    originals = known_files if isinstance(known_files, dict) else None
    patch = Patch()
    if m := SUMMARY_RE.search(output):
        for line in m.group("body").splitlines():
            line = line.strip().lstrip("-").strip()
            if ":" in line:
                k, v = line.split(":", 1)
                patch.summary[k.strip()] = v.strip()

    for m in FILE_RE.finditer(output):
        raw = m.group("path")
        try:
            path = check_path(raw)
        except UnsafePath as e:
            patch.rejected.append((raw, str(e)))
            continue
        if known_files is not None and path not in known_files and path not in patch.summary:
            patch.rejected.append((path, "not in bundle and not declared new in SUMMARY"))
            continue
        if path in patch.files:
            patch.rejected.append((path, "duplicate FILE block"))
            continue
        body = m.group("body") + "\n"
        if originals is not None and is_test_file(path):
            if reason := weakening_reason(originals.get(path), body):
                patch.rejected.append((path, f"test weakening: {reason}"))
                continue
        patch.files[path] = body
    # An opened FILE block without its END marker means the decode was cut off.
    patch.truncated = output.count("<<<FILE ") > output.count("<<<END FILE>>>")

    for m in DELETE_RE.finditer(output):
        raw = m.group("path")
        try:
            path = check_path(raw)
            if known_files is not None and path not in known_files:
                raise UnsafePath("cannot delete a file absent from the input bundle")
            if path in patch.files or path in patch.deletes:
                raise UnsafePath("conflicting or duplicate deletion")
            if is_test_file(path):
                raise UnsafePath("test weakening: deleting a test file is not allowed")
            patch.deletes.append(path)
        except UnsafePath as e:
            patch.rejected.append((raw, str(e)))
    return patch


def validate_patch(patch: Patch) -> None:
    if patch.truncated or patch.rejected:
        raise ValueError("patch is truncated or contains rejected changes; review required")
    if set(patch.files) & set(patch.deletes):
        raise ValueError("patch both writes and deletes the same file")
    for path in [*patch.files, *patch.deletes]:
        if check_path(path) != path:
            raise UnsafePath("patch paths must be normalized")


def patch_digest(patch: Patch) -> str:
    validate_patch(patch)
    payload = json.dumps({"files": patch.files, "deletes": sorted(patch.deletes)}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def unified_diff(path: str, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )
