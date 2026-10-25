"""PLAN: Argon lists every breaking change, thinking 'high' (SPEC §4 step 2). [CP2]"""

from __future__ import annotations

from . import gemini
from .jsonx import extract_json
from .models import Plan
from .pack import Bundle
from .prompts import load


def make_plan(
    bundle: Bundle,
    notes: str,
    from_v: str = "4.2",
    to_v: str = "5.2",
    *,
    framework: str = "Django",
    language: str = "Python",
) -> tuple[Plan, gemini.Result]:
    prompt = load(
        "plan",
        framework=framework,
        language=language,
        from_version=from_v,
        to_version=to_v,
        release_notes=notes,
        bundle=bundle.text,
    )
    res = gemini.ask(prompt, thinking_level="high", background=True, max_output_tokens=65536)
    return Plan.model_validate(extract_json(res.text)), res
