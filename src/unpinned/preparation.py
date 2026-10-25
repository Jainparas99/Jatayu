"""Prepare adapter-specific inputs without executing target code or calling models."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from .adapters import Adapter, get
from .config import settings
from .execution import ExecutionSpec
from .pack import Bundle
from .parse import Patch, validate_patch
from .repository import validate_django_version, validate_source
from .runs import new_run_id, run_dir, save_json


def resolve_adapter(
    name: str,
    *,
    source_version: str | None = None,
    target_version: str | None = None,
    framework: str | None = None,
    language: str | None = None,
    test_command: str | None = None,
    install_command: str | None = None,
    check_command: str | None = None,
    notes_urls: list[str] | None = None,
) -> tuple[Adapter, str, str]:
    """Generic inputs must be explicit; do not inherit framework-specific defaults."""
    if name == "generic":
        required = {
            "--from-version": source_version,
            "--target": target_version,
            "--framework": framework,
            "--language": language,
            "--test-cmd": test_command,
            "--install-cmd": install_command,
        }
        missing = [flag for flag, value in required.items() if not value or not value.strip()]
        if not notes_urls:
            missing.append("--notes-url")
        if missing:
            raise ValueError("generic preparation requires " + ", ".join(missing))
        adapter = get(
            name,
            framework=framework,
            language=language,
            test_command=test_command,
            install_command=install_command,
            check_command=check_command,
            notes_urls=notes_urls,
        )
    else:
        adapter = get(name)
        if any(
            value is not None
            for value in (
                framework,
                language,
                test_command,
                install_command,
                check_command,
                notes_urls,
            )
        ):
            raise ValueError(
                "custom commands, framework, language and notes require --adapter generic"
            )
        s = settings()
        source_version = source_version or s.baseline_django
        target_version = target_version or s.target_django
        validate_django_version(source_version)
        validate_django_version(target_version)
    for version in (source_version, target_version):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,63}", version or ""):
            raise ValueError("versions must be nonempty version identifiers")
    if source_version == target_version:
        raise ValueError("source and target versions must differ")
    if adapter.roadmap:
        raise ValueError("this adapter is a roadmap entry, not an executable adapter")
    return adapter, source_version, target_version


def recipe(
    adapter: Adapter,
    bundle: Bundle,
    repo_url: str,
    source_commit: str,
    source_version: str,
    target_version: str,
    *,
    execution_spec: ExecutionSpec | None = None,
) -> dict:
    """An inventory and requested execution recipe; never migration evidence."""
    validate_source(repo_url, source_commit)
    if bundle.skipped:
        raise ValueError(
            f"input bundle omitted {len(bundle.skipped)} files; review before migration"
        )
    if not bundle.files:
        raise ValueError("input bundle contains no source files")
    if execution_spec is not None:
        execution_spec.check_repository(repo_url)
        if execution_spec.source_commit and execution_spec.source_commit != source_commit:
            raise ValueError("prepared commit differs from execution recipe")
        if (adapter.name, adapter.framework, adapter.language, source_version, target_version) != (
            execution_spec.adapter,
            execution_spec.framework,
            execution_spec.language,
            execution_spec.source_version,
            execution_spec.target_version,
        ):
            raise ValueError("prepared adapter differs from execution recipe")
        working = bundle.root / execution_spec.working_directory
        if not working.is_dir() or not working.resolve().is_relative_to(bundle.root.resolve()):
            raise ValueError("recipe working directory is missing or escapes the repository")
    urls = adapter.notes_urls(source_version, target_version)
    for url in urls:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("upgrade notes must use HTTPS URLs without embedded credentials")

    def command(value: str | None) -> str | None:
        if value is None:
            return None
        return value.replace("{version}", target_version).replace(
            "{minor}", ".".join(target_version.split(".")[:2])
        )

    value = {
        "schema_version": 1,
        "scope": "local_input_preparation",
        "artifacts_verified": False,
        "ready_for_review": False,
        "adapter": adapter.name,
        "framework": adapter.framework,
        "language": adapter.language,
        "repo_url": repo_url,
        "source_commit": source_commit,
        "requested_source_version": source_version,
        "requested_target_version": target_version,
        "bundle_sha256": bundle.sha256,
        "files": sorted(bundle.files),
        "notes_urls": urls,
        "install_command": command(adapter.install_command),
        "test_command": command(adapter.test_command),
        "check_command": command(adapter.check_command),
        "baseline_command": command(adapter.baseline_command),
        "limitations": [
            "Commands and requested runtime versions have not been executed or verified.",
            "Preparation cannot establish target exposure or enable approval.",
        ],
    }
    if execution_spec is not None:
        value["execution_spec"] = execution_spec.model_dump(mode="json")
        value["source_install_command"] = execution_spec.render(
            execution_spec.install_command, source_version
        )
        value["source_test_command"] = execution_spec.render(
            execution_spec.test_command, source_version
        )
    return value


def save_recipe(value: dict):
    directory = run_dir(new_run_id("prepare"))
    save_json(directory / "input.json", value)
    return directory


def bump_only(bundle: Bundle, target: str, adapter: Adapter) -> Patch:
    patch = adapter.bump(bundle.files, target)
    validate_patch(patch)
    if not patch.files and not patch.deletes:
        raise ValueError(
            "the adapter produced no dependency changes; B0 is unavailable for this input"
        )
    return patch
