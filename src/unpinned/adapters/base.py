"""The adapter contract. Five things vary per ecosystem; nothing else does."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..parse import Patch

Files = dict[str, str]  # relpath -> content (a pack.Bundle's files)


@dataclass(frozen=True)
class Adapter:
    name: str  # registry key, e.g. "django"
    framework: str  # shown to Argon and in the UI, e.g. "Django"
    language: str  # e.g. "Python"
    # 1. Which files Argon reads. None = every UTF-8 text file (language-agnostic mode).
    include_suffixes: frozenset[str] | None
    include_names: frozenset[str] = frozenset()
    # 2. How to bump the framework pin (baseline B0 and the target for MIGRATE).
    bump: Callable[[Files, str], Patch] = field(default=lambda files, target: Patch())
    # 3. Official upgrade notes Argon gets in context: (from_version, to_version) -> URLs.
    notes_urls: Callable[[str, str], list[str]] = field(default=lambda a, b: [])
    # 4. What the sandbox runs. {version} is replaced with the framework version under test.
    install_command: str = ""
    test_command: str = ""
    check_command: str | None = None
    # 5. Deterministic rule-based baseline (B1), or None if the ecosystem has none.
    baseline_command: str | None = None
    detect: Callable[[Path], bool] = field(default=lambda root: False)
    roadmap: bool = False  # True = described, not yet proven by a saved run

    def wants(self, rel: Path) -> bool | None:
        """True/False by suffix or name; None means 'decide by sniffing for text'."""
        if rel.name in self.include_names:
            return True
        if self.include_suffixes is None:
            return None
        return rel.suffix in self.include_suffixes
