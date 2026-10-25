"""Django release notes as context (SPEC §4 step 1). [CP2]

Fetches the official release notes and caches them in context/. Trim to the
"Backwards incompatible changes" and "Features removed" sections if the full text is too long.
"""

from __future__ import annotations

import re

import httpx

from .config import settings

VERSIONS = ["5.0", "5.1", "5.2"]
URL = "https://docs.djangoproject.com/en/{v}/releases/{v}/"


def _strip_html(html: str) -> str:
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S)
    text = re.sub(r"<[^>]+>", "", html)
    return re.sub(r"\n\s*\n+", "\n\n", text)


def release_notes(versions: list[str] = VERSIONS) -> str:
    out = []
    cache = settings().context_dir
    cache.mkdir(exist_ok=True)
    for v in versions:
        path = cache / f"django-{v}-release-notes.txt"
        if not path.exists():
            r = httpx.get(URL.format(v=v), timeout=30, follow_redirects=True)
            r.raise_for_status()
            path.write_text(_strip_html(r.text))
        out.append(f"--- Django {v} release notes ---\n{path.read_text()}")
    return "\n\n".join(out)


def notes_for(adapter, from_version: str, to_version: str) -> str:
    """Upgrade notes for any adapter, cached in context/ by URL hash."""
    import hashlib

    cache = settings().context_dir
    cache.mkdir(exist_ok=True)
    out = []
    for url in adapter.notes_urls(from_version, to_version):
        path = cache / f"notes-{hashlib.sha256(url.encode()).hexdigest()[:16]}.txt"
        if not path.exists():
            r = httpx.get(url, timeout=30, follow_redirects=True)
            r.raise_for_status()
            path.write_text(_strip_html(r.text))
        out.append(f"--- {adapter.framework} upgrade notes: {url} ---\n{path.read_text()}")
    return "\n\n".join(out)
