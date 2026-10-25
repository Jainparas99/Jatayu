"""Read framework/runtime versions out of dependency manifests (no code execution).

Lock files win over loose constraints because they say what actually ships.
Each finding records the file and line it came from, so every claim is checkable.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Confidence = Literal["locked", "pinned", "constraint", "declared"]
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "vendor", "dist", "build", "__pycache__"}
MAX_DEPTH = 3  # monorepos: look a few levels down, not through the whole tree


@dataclass(frozen=True)
class Finding:
    product: str  # catalog key: django, rails, spring-boot, python, nodejs, ruby
    version: str
    source: str  # relative path
    line: int
    confidence: Confidence


_VER = r"(\d+(?:\.\d+){0,3})"
_RANK = {"locked": 0, "pinned": 1, "constraint": 2, "declared": 3}


def _lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []


def _files(root: Path) -> list[Path]:
    out = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if len(rel.parts) > MAX_DEPTH or any(part in SKIP_DIRS for part in rel.parts[:-1]):
            continue
        if p.is_file() and not p.is_symlink():
            out.append(p)
    return out


# --- Python / Django -------------------------------------------------------------------------

_REQ = re.compile(r"(?i)^\s*django\s*(?:\[[^\]]*\])?\s*(==|~=|>=|>)\s*" + _VER)
_TOML_DEP = re.compile(r"""(?i)["']django\s*(?:\[[^\]]*\])?\s*(==|~=|>=|>)\s*""" + _VER)
_POETRY = re.compile(r"""(?i)^\s*django\s*=\s*["']?[\^~>=]*\s*""" + _VER)
_LOCK_NAME = re.compile(r'(?i)^\s*name\s*=\s*"django"\s*$')
_LOCK_VER = re.compile(r'^\s*version\s*=\s*"' + _VER + '"')
_REQUIRES_PY = re.compile(r"""requires-python\s*=\s*["'][^0-9]*""" + _VER)
_FROM_PY = re.compile(r"(?i)^\s*FROM\s+(?:\S+/)?python:" + _VER)
_FROM_NODE = re.compile(r"(?i)^\s*FROM\s+(?:\S+/)?node:" + r"(\d+(?:\.\d+){0,2})")


def _python(root: Path, f: Path, rel: str) -> list[Finding]:
    name, out = f.name, []
    lines = _lines(f)
    if name.startswith("requirements") and name.endswith((".txt", ".in")):
        for i, line in enumerate(lines, 1):
            if m := _REQ.search(line):
                conf: Confidence = "pinned" if m.group(1) == "==" else "constraint"
                out.append(Finding("django", m.group(2), rel, i, conf))
    elif name in ("pyproject.toml", "Pipfile"):
        for i, line in enumerate(lines, 1):
            if m := _TOML_DEP.search(line):
                conf = "pinned" if m.group(1) == "==" else "constraint"
                out.append(Finding("django", m.group(2), rel, i, conf))
            elif m := _POETRY.search(line):
                out.append(Finding("django", m.group(1), rel, i, "constraint"))
            if m := _REQUIRES_PY.search(line):
                out.append(Finding("python", m.group(1), rel, i, "declared"))
    elif name in ("poetry.lock", "uv.lock", "Pipfile.lock"):
        if name == "Pipfile.lock":
            try:
                data = json.loads("\n".join(lines))
                v = data.get("default", {}).get("django", {}).get("version", "")
                if m := re.search(_VER, v):
                    out.append(Finding("django", m.group(1), rel, 1, "locked"))
            except ValueError:
                pass
        else:
            for i, line in enumerate(lines):
                if _LOCK_NAME.match(line) and i + 1 < len(lines):
                    if m := _LOCK_VER.match(lines[i + 1]):
                        out.append(Finding("django", m.group(1), rel, i + 2, "locked"))
    elif name in (".python-version", "runtime.txt"):
        for i, line in enumerate(lines, 1):
            if m := re.search(r"(?:python-)?" + _VER, line.strip()):
                out.append(Finding("python", m.group(1), rel, i, "pinned"))
                break
    return out


# --- Ruby / Rails ----------------------------------------------------------------------------

_GEMLOCK = re.compile(r"^\s{4}rails \(" + _VER + r"\)")
_GEMFILE = re.compile(r"""^\s*gem\s+["']rails["']\s*,\s*["'][~>=<\s]*""" + _VER)


_RUBY_VERSION_FILE = re.compile(r"^\s*(?:ruby-)?" + _VER + r"\s*$")
_GEMFILE_RUBY = re.compile(r"""^\s*ruby\s+["']\s*[~>=<]*\s*""" + _VER)
_GEMSPEC_RUBY = re.compile(r"""required_ruby_version\s*=\s*["'][~>=<\s]*""" + _VER)
_TOOL_VERSIONS_RUBY = re.compile(r"^\s*ruby\s+" + _VER)
_FROM_RUBY = re.compile(r"(?i)^\s*FROM\s+(?:\S+/)?ruby:" + _VER)


def _ruby_runtime(f: Path, rel: str) -> list[Finding]:
    """Ruby interpreter versions: pinned files beat declared minimums."""
    table = {
        ".ruby-version": (_RUBY_VERSION_FILE, "pinned"),
        ".tool-versions": (_TOOL_VERSIONS_RUBY, "pinned"),
        "Gemfile": (_GEMFILE_RUBY, "pinned"),
    }
    pat, conf = table.get(f.name, (None, None))
    if pat is None and f.name.endswith(".gemspec"):
        pat, conf = _GEMSPEC_RUBY, "declared"
    if pat is None:
        return []
    for i, line in enumerate(_lines(f), 1):
        if m := pat.search(line):
            return [Finding("ruby", m.group(1), rel, i, conf)]  # type: ignore[arg-type]
    return []


def _ruby(f: Path, rel: str) -> list[Finding]:
    out = []
    pat, conf = {
        "Gemfile.lock": (_GEMLOCK, "locked"),
        "Gemfile": (_GEMFILE, "constraint"),
    }.get(f.name, (None, None))
    if pat is None:
        return out
    for i, line in enumerate(_lines(f), 1):
        if m := pat.search(line):
            out.append(Finding("rails", m.group(1), rel, i, conf))  # type: ignore[arg-type]
            break
    return out


# --- Java / Spring Boot ----------------------------------------------------------------------

_POM_PARENT = re.compile(
    r"<parent>.*?<artifactId>\s*spring-boot-starter-parent\s*</artifactId>.*?"
    r"<version>\s*" + _VER,
    re.S,
)
_GRADLE = re.compile(r"""org\.springframework\.boot["')]*\s*version\s*["']""" + _VER)


def _java(f: Path, rel: str) -> list[Finding]:
    text = "\n".join(_lines(f))
    if f.name == "pom.xml":
        if m := _POM_PARENT.search(text):
            line = text[: m.start(1)].count("\n") + 1
            return [Finding("spring-boot", m.group(1), rel, line, "pinned")]
    elif f.name in ("build.gradle", "build.gradle.kts"):
        if m := _GRADLE.search(text):
            line = text[: m.start(1)].count("\n") + 1
            return [Finding("spring-boot", m.group(1), rel, line, "pinned")]
    return []


# --- Node / runtimes in Docker ---------------------------------------------------------------


def _node(f: Path, rel: str) -> list[Finding]:
    if f.name == ".nvmrc":
        for i, line in enumerate(_lines(f), 1):
            if m := re.search(r"v?(\d+(?:\.\d+){0,2})", line):
                return [Finding("nodejs", m.group(1), rel, i, "pinned")]
    if f.name == "package.json":
        lines = _lines(f)
        try:
            engines = json.loads("\n".join(lines)).get("engines", {}) or {}
        except ValueError:
            return []
        node = engines.get("node") if isinstance(engines, dict) else None
        if isinstance(node, str) and (m := re.search(r"(\d+(?:\.\d+){0,2})", node)):
            line = next((i for i, s in enumerate(lines, 1) if '"node"' in s), 1)
            return [Finding("nodejs", m.group(1), rel, line, "declared")]
    return []


def _docker(f: Path, rel: str) -> list[Finding]:
    if not (f.name == "Dockerfile" or f.name.startswith("Dockerfile.")):
        return []
    out = []
    for i, line in enumerate(_lines(f), 1):
        if m := _FROM_PY.search(line):
            out.append(Finding("python", m.group(1), rel, i, "pinned"))
        elif m := _FROM_NODE.search(line):
            out.append(Finding("nodejs", m.group(1), rel, i, "pinned"))
        elif m := _FROM_RUBY.search(line):
            out.append(Finding("ruby", m.group(1), rel, i, "pinned"))
    return out


def detect(root: Path) -> list[Finding]:
    """All findings, then the most trustworthy one per (product, directory)."""
    root = root.resolve()
    raw: list[Finding] = []
    for f in _files(root):
        rel = f.relative_to(root).as_posix()
        raw += _python(root, f, rel) + _ruby(f, rel) + _ruby_runtime(f, rel)
        raw += _java(f, rel) + _node(f, rel)
        raw += _docker(f, rel)
    best: dict[tuple[str, str], Finding] = {}
    for fd in raw:
        key = (fd.product, str(Path(fd.source).parent))
        cur = best.get(key)
        if cur is None or _RANK[fd.confidence] < _RANK[cur.confidence]:
            best[key] = fd
    return sorted(best.values(), key=lambda x: (x.product, x.source))
