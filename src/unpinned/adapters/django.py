"""Django adapter (tested). Upgrade path: 4.2 LTS → 5.2 LTS."""

from __future__ import annotations

import re
from pathlib import Path

from ..parse import Patch
from .base import Adapter, Files

# Feature releases in order; notes for every release after `from` up to `to` go to Argon.
SERIES = ["3.2", "4.0", "4.1", "4.2", "5.0", "5.1", "5.2", "6.0", "6.1"]
NOTES_URL = "https://docs.djangoproject.com/en/{v}/releases/{v}/"

_REQ_PIN = re.compile(r"(?im)^(\s*)django\s*(\[[^\]]*\])?\s*([<>=!~][^#\n]*?)?(\s*#.*)?$")
_TOML_PIN = re.compile(r"""(?i)(["'])django\s*(\[[^\]]*\])?\s*[<>=!~][^"']*\1""")


def _minor(version: str) -> str:
    return ".".join(version.split(".")[:2])


def notes_urls(from_version: str, to_version: str) -> list[str]:
    a, b = SERIES.index(_minor(from_version)), SERIES.index(_minor(to_version))
    if b <= a:
        raise ValueError(f"target {to_version} is not newer than {from_version}")
    return [NOTES_URL.format(v=v) for v in SERIES[a + 1 : b + 1]]


def bump(files: Files, target: str) -> Patch:
    """Change only the Django pin in requirements*.txt / *.in and pyproject.toml."""
    p = Patch()
    for path, content in files.items():
        name = Path(path).name
        if name.startswith("requirements") and name.endswith((".txt", ".in")):
            new = _REQ_PIN.sub(lambda m: f"{m.group(1)}Django=={target}{m.group(4) or ''}", content)
        elif name == "pyproject.toml":
            new = _TOML_PIN.sub(lambda m: f"{m.group(1)}Django=={target}{m.group(1)}", content)
        else:
            continue
        if new != content:
            p.files[path] = new
    return p


def detect(root: Path) -> bool:
    if any(root.glob("manage.py")) or any(root.glob("*/manage.py")):
        return True
    for name in ("requirements.txt", "pyproject.toml", "setup.cfg", "setup.py"):
        f = root / name
        if f.is_file() and re.search(r"(?i)\bdjango\b", f.read_text(errors="ignore")):
            return True
    return False


DJANGO = Adapter(
    name="django",
    framework="Django",
    language="Python",
    include_suffixes=frozenset(
        {".py", ".html", ".txt", ".cfg", ".toml", ".ini", ".in", ".yaml", ".yml", ".json"}
    ),
    include_names=frozenset(
        {"requirements.txt", "setup.py", "setup.cfg", "pyproject.toml", "tox.ini", "manage.py"}
    ),
    bump=bump,
    notes_urls=notes_urls,
    install_command='pip install -r requirements.txt && pip install "Django=={version}"',
    test_command="python manage.py test",
    check_command="python manage.py check",
    baseline_command="git ls-files -z -- '*.py' | xargs -0 django-upgrade --target-version {minor}",
    detect=detect,
)
