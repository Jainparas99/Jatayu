"""Validate public input repositories and immutable revisions before tool use."""

import re
from urllib.parse import urlsplit


def validate_source(url: str, commit: str | None = None) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or parsed.query
        or parsed.fragment
        or not re.fullmatch(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?", parsed.path)
    ):
        raise ValueError("Use a public https://github.com/owner/repository URL.")
    if commit is not None and not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Verification requires an immutable 40-character Git commit.")


def validate_django_version(version: str) -> None:
    if not re.fullmatch(r"[45]\.2\.[0-9]+", version):
        raise ValueError("Use an exact Django 4.2.x or 5.2.x version, including the patch number.")
