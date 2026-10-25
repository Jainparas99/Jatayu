"""`python -m unpinned.fleet scan <path|github-url>... [--fail-on eol] [--json] [--github]`

Also: `python -m unpinned.fleet refresh-eol` to update the catalog from endoflife.date.
Targets can be read from a file with `@repos.txt` (one per line, # comments allowed).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .scan import save, scan_many

ICON = {"critical": "✖", "high": "✖", "medium": "!", "low": "·", "none": "✓"}


def _targets(args: list[str]) -> list[str]:
    out = []
    for a in args:
        if a.startswith("@"):
            for line in Path(a[1:]).read_text().splitlines():
                line = line.split("#", 1)[0].strip()
                if line:
                    out.append(line)
        else:
            out.append(a)
    return out


def _print(result: dict) -> None:
    s = result["summary"]
    print(
        f"Fleet: {s['repos']} repos · {s['eol_components']} end-of-life components · "
        f"{s['expiring_components']} expiring · {s['jatayu_ready']} upgradable by Jatayu now"
    )
    print(f"(support dates from {result['catalog_source']}, as of {result['catalog_as_of']})\n")
    for r in result["repos"]:
        print(f"{ICON[r['severity']]} {r['target']}  [{r['severity']}]")
        if r["error"]:
            print(f"    error: {r['error']}")
        for c in r["components"]:
            st, fd = c["status"], c["finding"]
            where = f"{fd['source']}:{fd['line']}"
            if st["status"] == "eol":
                state = f"END OF LIFE since {st['eol']} ({st['days_overdue']} days)"
            elif st["status"] == "expiring":
                state = f"support ends {st['eol']} ({st['days_left']} days left)"
            elif st["status"] == "supported":
                state = f"supported until {st['eol']}"
            else:
                state = "unknown release"
            target = (
                f" → {st['recommended']} ({st['recommended_latest']})" if st["recommended"] else ""
            )
            print(f"    {c['label']} {fd['version']}: {state}{target}  [{where}, {c['engine']}]")
        print()


def _annotate(result: dict) -> None:
    """GitHub Actions workflow commands, so findings show up on the PR's files."""
    for r in result["repos"]:
        for c in r["components"]:
            st, fd = c["status"], c["finding"]
            if st["status"] not in ("eol", "expiring"):
                continue
            level = "error" if st["status"] == "eol" else "warning"
            msg = (
                f"{c['label']} {fd['version']} "
                + ("reached end of life on " if st["status"] == "eol" else "loses support on ")
                + st["eol"]
                + (f"; upgrade to {st['recommended']}" if st["recommended"] else "")
            )
            print(f"::{level} file={fd['source']},line={fd['line']},title=Jatayu::{msg}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m unpinned.fleet")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("scan", help="scan repos for end-of-life frameworks and runtimes")
    sc.add_argument("targets", nargs="+", help="local paths, https://github.com/o/r, or @file")
    sc.add_argument("--json", action="store_true", help="print JSON instead of text")
    sc.add_argument("--github", action="store_true", help="emit GitHub Actions annotations")
    sc.add_argument("--save", action="store_true", help="save under runs/fleet/ for the dashboard")
    sc.add_argument(
        "--fail-on",
        choices=["eol", "expiring", "never"],
        default="never",
        help="exit 1 when any component is end of life (or expiring)",
    )
    sub.add_parser("refresh-eol", help="update support dates from endoflife.date")
    a = ap.parse_args(argv)

    if a.cmd == "refresh-eol":
        from .eol import refresh

        print(f"saved {refresh()}")
        return 0

    result = scan_many(_targets(a.targets))
    if a.save:
        from ..config import settings

        print(f"saved {save(result, settings().runs_dir)}", file=sys.stderr)
    if a.json:
        print(json.dumps(result, indent=1))
    else:
        _print(result)
    if a.github:
        _annotate(result)
    s = result["summary"]
    if a.fail_on == "eol" and s["eol_components"]:
        return 1
    if a.fail_on == "expiring" and (s["eol_components"] or s["expiring_components"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
