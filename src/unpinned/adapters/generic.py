"""Language-agnostic adapter: any repo, any language.

Argon reads every UTF-8 text file (binaries, vendored dirs and secrets are skipped by pack).
You supply what can't be guessed: the test command, the install command, and the upgrade
notes. The verification loop and the Approve gate are identical to the Django path.
"""

from __future__ import annotations

from .base import Adapter


def generic(
    *,
    framework: str = "the project's framework",
    language: str = "any",
    test_command: str,
    install_command: str = "",
    check_command: str | None = None,
    notes_urls: list[str] | None = None,
) -> Adapter:
    if not test_command.strip():
        raise ValueError("generic adapter needs a test command (e.g. 'bundle exec rspec')")
    urls = list(notes_urls or [])
    return Adapter(
        name="generic",
        framework=framework,
        language=language,
        include_suffixes=None,  # every text file
        notes_urls=lambda a, b: urls,
        install_command=install_command,
        test_command=test_command,
        check_command=check_command,
        roadmap=False,
    )
