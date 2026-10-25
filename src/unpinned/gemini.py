"""The ONLY module that calls the Gemini SDK (AGENTS.md invariant 8).

Written from the hackathon builder guide. Verify field names with the
`gemini-api-dev` skill on first use; if the SDK differs, fix it here and log the
quirk in docs/internal/HANDOFF.md.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .config import ANTIGRAVITY, ARGON, GENERIC_EXTRA_DOMAINS, SANDBOX_ALLOWLIST, settings

ThinkingLevel = str  # "low" | "medium" | "high"
_PENDING = ("in_progress", "queued")


@dataclass
class Result:
    id: str
    text: str
    status: str
    raw: Any
    input_tokens: int | None = None
    output_tokens: int | None = None
    environment_id: str | None = None


_CLIENT = None


def client():
    """One shared client for the process.

    A throwaway client (client().interactions.create(...)) is garbage-collected right away
    and closes its HTTP connection mid-request: "Cannot send a request, as the client has
    been closed." Keep a single reference instead.
    """
    global _CLIENT
    if _CLIENT is None:
        from google import genai  # imported lazily so tests run without the SDK configured

        key = settings().gemini_api_key
        if not key:
            raise RuntimeError(
                "Set GEMINI_API_KEY in the project .env before live Gemini execution."
            )
        _CLIENT = genai.Client(api_key=key)
    return _CLIENT


def _usage(interaction: Any) -> tuple[int | None, int | None]:
    usage = getattr(interaction, "usage", None) or getattr(interaction, "usage_metadata", None)
    if usage is None:
        return None, None
    get = (
        (lambda k: usage.get(k)) if isinstance(usage, dict) else (lambda k: getattr(usage, k, None))
    )

    def first(*keys):
        return next((get(k) for k in keys if get(k) is not None), None)

    return (
        first("total_input_tokens", "input_tokens", "prompt_token_count"),
        first("total_output_tokens", "output_tokens", "candidates_token_count"),
    )


def _wrap(interaction: Any) -> Result:
    i, o = _usage(interaction)

    def get(obj, key, default=None):
        return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)

    chunks = [
        get(content, "text", "") or ""
        for step in (get(interaction, "steps", []) or [])
        if get(step, "type") == "model_output"
        for content in (get(step, "content", []) or [])
        if get(content, "type") == "text"
    ]
    return Result(
        id=getattr(interaction, "id", ""),
        text="".join(chunks) if chunks else getattr(interaction, "output_text", "") or "",
        status=getattr(interaction, "status", "unknown") or "unknown",
        raw=interaction,
        input_tokens=i,
        output_tokens=o,
        environment_id=getattr(interaction, "environment_id", None),
    )


def _completed(result: Result) -> Result:
    if result.status != "completed":
        raise RuntimeError(f"Gemini interaction {result.id} ended with status {result.status}")
    return result


def wait(interaction_id: str, poll_seconds: float = 5.0, timeout: float = 3600) -> Result:
    c = client()
    start = time.monotonic()
    while True:
        it = c.interactions.get(id=interaction_id, timeout=60)
        if getattr(it, "status", None) not in _PENDING:
            return _completed(_wrap(it))
        if time.monotonic() - start > timeout:
            raise TimeoutError(f"interaction {interaction_id} still {it.status} after {timeout}s")
        time.sleep(poll_seconds)


def ask(
    prompt: str,
    *,
    model: str = ARGON,
    thinking_level: ThinkingLevel = "medium",
    max_output_tokens: int | None = None,
    background: bool = False,
    previous_interaction_id: str | None = None,
) -> Result:
    """One model call. background=True is required for output > 65,536 tokens."""
    config: dict[str, Any] = {"thinking_level": thinking_level}
    if thinking_level not in {"low", "medium", "high"}:
        raise ValueError("invalid thinking level")
    if max_output_tokens and max_output_tokens > 65536 and not background:
        raise ValueError("long decode requires background=True")
    if max_output_tokens:
        config["max_output_tokens"] = max_output_tokens
    kwargs: dict[str, Any] = {"model": model, "input": prompt, "generation_config": config}
    if background:
        kwargs["background"] = True
    if previous_interaction_id:
        kwargs["previous_interaction_id"] = previous_interaction_id
    it = client().interactions.create(**kwargs, timeout=1200)
    if getattr(it, "status", None) in _PENDING:
        return wait(it.id)
    return _completed(_wrap(it))


def run_agent(
    instruction: str,
    *,
    allowlist: list[str] | None = None,
    previous_interaction_id: str | None = None,
    environment_id: str | None = None,
    background: bool = True,
    sources: list[dict] | None = None,
) -> Result:
    """Run the Antigravity managed agent (Argon inside a Google-hosted Linux sandbox).

    sources: files mounted into a NEW environment, e.g. {"type": "inline", "target": path,
    "encoding": "base64", "content": ...}. Ignored when continuing an existing environment.
    """
    if previous_interaction_id and not environment_id:
        raise ValueError("continuing a managed agent requires its environment_id")
    domains = SANDBOX_ALLOWLIST if allowlist is None else allowlist
    if any(domain not in SANDBOX_ALLOWLIST + GENERIC_EXTRA_DOMAINS for domain in domains):
        raise ValueError("domain is outside the configured sandbox allowlist")
    kwargs: dict[str, Any] = {
        "agent": ANTIGRAVITY,
        "agent_config": {"type": "antigravity", "model": ARGON},
        "input": instruction,
        "environment": environment_id
        or {
            "type": "remote",
            "network": {"allowlist": [{"domain": domain} for domain in domains]}
            if domains
            else "disabled",
            **({"sources": sources} if sources else {}),
        },
    }
    if previous_interaction_id:
        kwargs["previous_interaction_id"] = previous_interaction_id
    if background:
        kwargs["background"] = True
    it = client().interactions.create(**kwargs, timeout=1200)
    if getattr(it, "status", None) in _PENDING:
        return wait(it.id)
    return _completed(_wrap(it))


def download_file(environment_id: str, path: str) -> bytes:
    """Raw bytes of a file in a managed-agent environment's snapshot (Files API)."""
    data = client().environments.files.download(environment=environment_id, path=path)
    if not isinstance(data, bytes | bytearray):
        raise RuntimeError(f"unexpected download result for {path}")
    return bytes(data)


def register_github_token(token: str, name: str = "unpinned-github") -> Any:
    """Register the GitHub token with the Credentials API so it's injected at the proxy.

    CP4: confirm the exact signature of client.credentials.create with the skill or a mentor.
    """
    if not token:
        raise ValueError("GitHub token is empty")
    return client().credentials.create(id=name, type="bearer_token", token=token)
