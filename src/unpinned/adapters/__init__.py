"""Ecosystem adapters: everything language- or framework-specific lives here.

The pipeline (pack → plan → migrate → verify → fix → approve) is the same for every
ecosystem. An adapter supplies only: which files to read, how to bump the version pin,
which upgrade notes to give Argon, how to install/test/check, and the rule-based baseline.

Shipped and tested today: `django`. `generic` works for any repo when you pass the test
command and notes yourself. Other ecosystems (Rails, Spring Boot) are roadmap: add a module
here; never claim one works until a real run under runs/ shows it.
"""

from __future__ import annotations

from pathlib import Path

from .base import Adapter
from .django import DJANGO
from .generic import generic

REGISTRY: dict[str, Adapter] = {DJANGO.name: DJANGO}


def get(name: str, **generic_options: object) -> Adapter:
    if name == "generic":
        return generic(**generic_options)  # type: ignore[arg-type]
    try:
        return REGISTRY[name]
    except KeyError:
        known = ", ".join([*REGISTRY, "generic"])
        raise ValueError(f"unknown adapter {name!r}; known: {known}") from None


def detect(root: Path) -> Adapter | None:
    """Return the first registered adapter that recognizes the repo, else None."""
    for adapter in REGISTRY.values():
        if adapter.detect(root):
            return adapter
    return None


__all__ = ["Adapter", "REGISTRY", "detect", "get"]
