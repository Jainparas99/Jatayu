"""Repo → one text bundle for Argon's context (SPEC §4 step 1)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .adapters import Adapter

INCLUDE_SUFFIXES = {".py", ".html", ".txt", ".cfg", ".toml", ".ini", ".in", ".yaml", ".yml"}
INCLUDE_NAMES = {
    "requirements.txt",
    "setup.py",
    "setup.cfg",
    "pyproject.toml",
    "tox.ini",
    "manage.py",
}
EXCLUDE_DIRS = {
    ".git",
    ".github",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    "static",
    "staticfiles",
    "media",
    "dist",
    "build",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "vendor",
    "site-packages",
    "htmlcov",
}
SECRET_NAMES = {
    ".env",
    "secrets.py",
    "local_settings.py",
    "id_rsa",
    "credentials.json",
    ".npmrc",
    ".pypirc",
    ".netrc",
    ".yarnrc",
    ".yarnrc.yml",
    "id_ed25519",
    "id_ecdsa",
    "id_dsa",
}
MAX_FILE_BYTES = 200_000


@dataclass
class Bundle:
    root: Path
    files: dict[str, str] = field(default_factory=dict)  # relpath -> content
    skipped: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        parts = [f"<<<FILE {p}>>>\n{c}\n<<<END FILE>>>" for p, c in sorted(self.files.items())]
        return "\n".join(parts)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()

    @property
    def approx_tokens(self) -> int:
        # Rough (~4 chars/token). Use gemini count_tokens for the real number.
        return len(self.text) // 4


def _wanted(rel: Path, adapter: Adapter | None = None) -> bool | None:
    """True/False, or None = include only if the file sniffs as text (any-language mode)."""
    # Static JavaScript/TypeScript is application source in a generic repository.
    excluded = EXCLUDE_DIRS - {"static"} if adapter and adapter.name == "generic" else EXCLUDE_DIRS
    if any(part in excluded for part in rel.parts[:-1]):
        return False
    if rel.name in SECRET_NAMES or rel.name.startswith(".env"):
        return False
    if adapter is not None:
        return adapter.wants(rel)
    return rel.suffix in INCLUDE_SUFFIXES or rel.name in INCLUDE_NAMES


def _is_text(path: Path) -> bool:
    with path.open("rb") as f:
        head = f.read(8192)
    if b"\0" in head:
        return False
    try:
        head.decode("utf-8")
    except UnicodeDecodeError as e:
        return e.start > len(head) - 4  # a multi-byte char cut at the 8 KB boundary is fine
    return True


def pack(root: Path, max_total_bytes: int = 3_000_000, adapter: Adapter | None = None) -> Bundle:
    """Read the repo. With an adapter whose include_suffixes is None, every text file is read."""
    root = root.resolve()
    b = Bundle(root=root)
    total = 0
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root)
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            b.skipped.append(rel.as_posix())
            continue
        wanted = _wanted(rel, adapter)
        if wanted is False or (wanted is None and not _is_text(path)):
            continue
        size = path.stat().st_size
        if size > MAX_FILE_BYTES or total + size > max_total_bytes:
            b.skipped.append(rel.as_posix())
            continue
        try:
            b.files[rel.as_posix()] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            b.skipped.append(rel.as_posix())
            continue
        total += size
    return b
