"""Ruby on Rails adapter — ROADMAP (roadmap=True). Not proven by a saved run yet.

Shape is the same as Django: bump the pin, give Argon the official upgrade guide, run the
suite in the sandbox. Before marking it ready: prove one upgrade end to end under runs/.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..parse import Patch
from .base import Adapter, Files

GUIDE = "https://guides.rubyonrails.org/upgrading_ruby_on_rails.html"
_GEMFILE_PIN = re.compile(r"""(^\s*gem\s+["']rails["']\s*,\s*)["'][^"']*["']""", re.M)


def bump(files: Files, target: str) -> Patch:
    p = Patch()
    for path, content in files.items():
        if Path(path).name == "Gemfile":
            new = _GEMFILE_PIN.sub(lambda m: f'{m.group(1)}"~> {target}"', content)
            if new != content:
                p.files[path] = new
    return p


def detect(root: Path) -> bool:
    gemfile = root / "Gemfile"
    return gemfile.is_file() and bool(
        re.search(r"""gem\s+["']rails["']""", gemfile.read_text(errors="ignore"))
    )


RAILS = Adapter(
    name="rails",
    framework="Ruby on Rails",
    language="Ruby",
    include_suffixes=frozenset(
        {".rb", ".erb", ".rake", ".yml", ".yaml", ".ru", ".gemspec", ".lock"}
    ),
    include_names=frozenset({"Gemfile", "Gemfile.lock", "Rakefile", ".ruby-version"}),
    bump=bump,
    notes_urls=lambda a, b: [GUIDE],
    install_command="bundle update rails && bundle install",
    test_command="bin/rails test",
    check_command="bin/rails zeitwerk:check",
    baseline_command=None,  # no widely used deterministic rewriter; compare against bump-only
    detect=detect,
    roadmap=True,
)
