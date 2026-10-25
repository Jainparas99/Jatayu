from types import SimpleNamespace as NS

import pytest
from google.genai import interactions

from unpinned import gemini


def test_long_decode_keeps_all_hops_and_zero_usage():
    result = gemini._wrap(
        NS(
            id="i",
            status="completed",
            environment_id="env",
            output_text="last",
            usage={"input_tokens": 0, "output_tokens": 0},
            steps=[
                {"type": "model_output", "content": [{"type": "text", "text": "first"}]},
                {"type": "thought", "content": [{"type": "text", "text": "private"}]},
                {"type": "model_output", "content": [{"type": "text", "text": "last"}]},
            ],
        )
    )
    assert result.text == "firstlast"
    assert result.input_tokens == 0 and result.output_tokens == 0
    assert result.environment_id == "env"


def test_agent_network_schema_and_environment_reuse(monkeypatch):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return NS(id="i", status="completed", output_text="ok", environment_id="env")

    monkeypatch.setattr(gemini, "client", lambda: NS(interactions=NS(create=create)))
    gemini.run_agent("check", allowlist=["pypi.org"])
    config = calls[-1]["environment"]
    assert config["network"] == {"allowlist": [{"domain": "pypi.org"}]}
    interactions.Environment.model_validate(config)
    gemini.run_agent("continue", previous_interaction_id="i", environment_id="env")
    assert calls[-1]["environment"] == "env"
    with pytest.raises(ValueError):
        gemini.run_agent("continue", previous_interaction_id="i")


def test_failed_terminal_response_is_not_a_completed_migration(monkeypatch):
    monkeypatch.setattr(
        gemini,
        "client",
        lambda: NS(
            interactions=NS(create=lambda **_: NS(id="i", status="failed", output_text="partial"))
        ),
    )
    with pytest.raises(RuntimeError, match="failed"):
        gemini.ask("migrate")


def test_usage_reads_installed_sdk_field_names():
    assert gemini._usage(NS(usage={"total_input_tokens": 123, "total_output_tokens": 0})) == (
        123,
        0,
    )
