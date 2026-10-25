"""MIGRATE: one Argon long decode emits every changed file (SPEC §4 step 3, §6). [CP2]"""

from __future__ import annotations

from . import gemini
from .config import settings
from .models import Plan
from .pack import Bundle
from .parse import Patch, parse
from .prompts import load


def migrate(
    bundle: Bundle,
    notes: str,
    plan: Plan | None,
    *,
    from_v: str = "4.2",
    to_v: str = "5.2",
    thinking_level: str = "high",
    framework: str = "Django",
    language: str = "Python",
) -> tuple[Patch, gemini.Result]:
    prompt = load(
        "migrate",
        framework=framework,
        language=language,
        from_version=from_v,
        to_version=to_v,
        release_notes=notes,
        plan=plan.model_dump_json(indent=1) if plan else "(none: live mode)",
        bundle=bundle.text,
    )
    res = gemini.ask(
        prompt,
        thinking_level=thinking_level,
        background=True,
        max_output_tokens=settings().max_output_tokens,
    )
    return parse(res.text, known_files=set(bundle.files)), res


def fix(failures_text: str, previous_interaction_id: str, known: set[str], to_v: str = "5.2"):
    """Fix-loop turn: server-side state via previous_interaction_id."""
    res = gemini.ask(
        load("fix", to_version=to_v, failures=failures_text),
        thinking_level="high",
        background=True,
        max_output_tokens=settings().max_output_tokens,
        previous_interaction_id=previous_interaction_id,
    )
    return parse(res.text, known_files=known), res
