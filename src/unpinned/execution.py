"""Explicit execution recipes for arbitrary languages. This module never runs commands."""

from __future__ import annotations

import ipaddress
import json
import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .parse import check_path
from .repository import validate_source

_VERSION = re.compile(r"v?[0-9][A-Za-z0-9._+-]{0,63}")
MAX_RECIPE_BYTES = 64_000


class ExecutionSpec(BaseModel):
    """User-reviewed commands, executed only by Claude's managed sandbox backend.

    Commands are complete shell scripts, not arguments to a local shell. {version}
    is the sole placeholder; render it separately for the original and target run.
    The recipe establishes intent, never execution evidence or security remediation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    adapter: Literal["generic"] = "generic"
    framework: str
    language: str
    source_version: str
    target_version: str
    install_command: str
    test_command: str
    version_command: str
    runtime_command: str
    junit_path: str
    notes_urls: list[str] = Field(min_length=1)
    check_command: str | None = None
    working_directory: str = "."
    timeout_seconds: int = Field(default=900, ge=10, le=3600)
    repository_url: str | None = None
    source_commit: str | None = None

    @field_validator("framework", "language")
    @classmethod
    def _label(cls, value: str) -> str:
        if not value.strip() or len(value) > 128 or any(ord(c) < 32 for c in value):
            raise ValueError("framework and language must be short printable labels")
        return value.strip()

    @field_validator("source_version", "target_version")
    @classmethod
    def _version(cls, value: str) -> str:
        if not _VERSION.fullmatch(value):
            raise ValueError("use an exact version identifier, not a range or moving tag")
        return value

    @field_validator(
        "install_command", "test_command", "version_command", "runtime_command", "check_command"
    )
    @classmethod
    def _command(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip() or len(value) > 16_000 or "\x00" in value:
            raise ValueError("commands must be nonempty text without NUL bytes")
        # Verification has no publishing role, even when a recipe is hand-written.
        if re.search(r"\bgit\s+push\b|\bgh\s+pr\s+create\b", value):
            raise ValueError("verification commands may not publish branches or pull requests")
        return value

    @field_validator("junit_path", "working_directory")
    @classmethod
    def _path(cls, value: str, info) -> str:
        if value == "." and info.field_name == "working_directory":
            return value
        if check_path(value) != value:
            raise ValueError("use a normalized repository-relative path")
        return value

    @field_validator("notes_urls")
    @classmethod
    def _notes(cls, values: list[str]) -> list[str]:
        for value in values:
            parsed = urlsplit(value)
            host = (parsed.hostname or "").lower()
            if (
                parsed.scheme != "https"
                or not host
                or parsed.username
                or parsed.password
                or parsed.port not in (None, 443)
            ):
                raise ValueError("notes must be public HTTPS URLs without credentials")
            if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
                raise ValueError("notes must not point to a local service")
            try:
                address = ipaddress.ip_address(host)
            except ValueError:
                continue
            if not address.is_global:
                raise ValueError("notes must not point to a private address")
        return values

    @field_validator("repository_url")
    @classmethod
    def _repository(cls, value: str | None) -> str | None:
        if value is not None:
            validate_source(value)
        return value

    @field_validator("source_commit")
    @classmethod
    def _commit(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[0-9a-f]{40}", value):
            raise ValueError("source_commit must be an immutable 40-character Git SHA")
        return value

    @model_validator(mode="after")
    def _different_versions(self) -> ExecutionSpec:
        if self.source_version == self.target_version:
            raise ValueError("source and target versions must differ")
        return self

    def render(self, command: str | None, version: str) -> str | None:
        """Pure substitution; never evaluate recipe text on the controller."""
        self._version(version)
        return None if command is None else command.replace("{version}", version)

    def check_repository(self, repo_url: str) -> None:
        validate_source(repo_url)

        def canonical(url):
            return url.rstrip("/").removesuffix(".git").lower()

        if self.repository_url and canonical(self.repository_url) != canonical(repo_url):
            raise ValueError("execution recipe belongs to a different repository")


def load_execution_spec(path: Path, *, repo_url: str) -> ExecutionSpec:
    """Load a small JSON recipe; repository code/config never selects commands implicitly."""
    if path.stat().st_size > MAX_RECIPE_BYTES:
        raise ValueError("execution recipe exceeds the size limit")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate recipe key: {key}")
            result[key] = value
        return result

    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
    spec = ExecutionSpec.model_validate(value)
    spec.check_repository(repo_url)
    return spec
