"""Pull the JSON object out of a model reply (code fences, leading prose)."""

from __future__ import annotations

import json
import re

_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


def extract_json(text: str) -> dict:
    if m := _FENCE.search(text):
        return json.loads(m.group(1))
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in model output")
    return json.loads(text[start : end + 1])
