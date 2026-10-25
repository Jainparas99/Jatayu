"""Settings from .env. Secrets are read here and nowhere else."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

ARGON = "gemini-4-argon"
FLASH = "gemini-3.8-flash"
FLASH_LITE = "gemini-3.5-flash-lite"
ANTIGRAVITY = "antigravity-preview-09-2026"

# The sandbox may reach only these hosts (SPEC §11).
SANDBOX_ALLOWLIST = [
    "pypi.org",
    "files.pythonhosted.org",
    "github.com",
    "api.github.com",
    "codeload.github.com",
]
# Approved by the project owner on 2026-10-25 for generic (non-Django) runs only.
GENERIC_EXTRA_DOMAINS = ["registry.npmjs.org"]


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str = field(repr=False)
    github_token: str = field(repr=False)
    fork_owner: str
    target_django: str
    baseline_django: str
    max_iterations: int
    max_output_tokens: int
    runs_dir: Path
    context_dir: Path


def _option(name: str, default: str) -> str:
    """Prefer the public Jatayu setting; accept the original prefix for existing setups."""
    return os.getenv(f"JATAYU_{name}", os.getenv(f"UNPINNED_{name}", default))


def settings() -> Settings:
    iterations = int(_option("MAX_ITERATIONS", "4"))
    if not 1 <= iterations <= 4:
        raise ValueError("JATAYU_MAX_ITERATIONS must be between 1 and 4")
    return Settings(
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        github_token=os.getenv("GITHUB_TOKEN", ""),
        fork_owner=_option("FORK_OWNER", ""),
        target_django=_option("TARGET_DJANGO", "5.2.18"),
        baseline_django=_option("BASELINE_DJANGO", "4.2.30"),
        max_iterations=iterations,
        max_output_tokens=int(_option("MAX_OUTPUT_TOKENS", "262144")),
        runs_dir=ROOT / "runs",
        context_dir=ROOT / "context",
    )
