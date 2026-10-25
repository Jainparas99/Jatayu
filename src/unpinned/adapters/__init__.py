"""Ecosystem adapters: everything language- or framework-specific lives here.

The pipeline (pack → plan → migrate → verify → fix → approve) is the same for every
ecosystem. An adapter supplies only: which files to read, how to bump the version pin,
which upgrade notes to give Argon, how to install/test/check, and the rule-based baseline.

- REGISTRY: proven end to end (Django).
- ROADMAP: described and unit-tested, NOT proven by a saved run (Rails, Spring Boot).
  `get()` refuses them unless the caller passes allow_roadmap=True, so nothing claims them.
- `generic`: any repo in any language; the user supplies the test command and notes.
"""

from __future__ import annotations

from pathlib import Path

from .base import Adapter
from .django import DJANGO
from .generic import generic
from .rails import RAILS
from .spring import SPRING_BOOT

REGISTRY: dict[str, Adapter] = {DJANGO.name: DJANGO}
ROADMAP: dict[str, Adapter] = {RAILS.name: RAILS, SPRING_BOOT.name: SPRING_BOOT}


def get(name: str, *, allow_roadmap: bool = False, **generic_options: object) -> Adapter:
    if name == "generic":
        return generic(**generic_options)  # type: ignore[arg-type]
    if name in REGISTRY:
        return REGISTRY[name]
    if name in ROADMAP:
        if allow_roadmap:
            return ROADMAP[name]
        raise ValueError(f"adapter {name!r} is on the roadmap and not yet proven by a run")
    known = ", ".join([*REGISTRY, "generic"])
    raise ValueError(f"unknown adapter {name!r}; known: {known}")


def detect(root: Path, *, include_roadmap: bool = False) -> Adapter | None:
    """Return the first adapter that recognizes the repo, else None."""
    pool = [*REGISTRY.values(), *(ROADMAP.values() if include_roadmap else [])]
    for adapter in pool:
        if adapter.detect(root):
            return adapter
    return None


__all__ = ["REGISTRY", "ROADMAP", "Adapter", "detect", "get"]
