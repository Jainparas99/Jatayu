"""End-of-life catalog for the frameworks and runtimes Fleet recognizes.

Built-in snapshot from https://endoflife.date (fetched 2026-10-25). `refresh()` re-downloads
it into context/eol-cache.json; the scanner prefers that cache when present. Dates are the
end of *community/OSS* security support; commercial extended support is noted separately.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

CATALOG_AS_OF = "2026-10-25"
SOURCE = "https://endoflife.date/api/{product}.json"

Status = Literal["eol", "expiring", "supported", "unknown"]
EXPIRING_DAYS = 180

# product -> list of {cycle, releaseDate, eol, lts?, extendedSupport?, latest}
BUILTIN: dict[str, list[dict]] = {
    "django": [
        {
            "cycle": "3.2",
            "releaseDate": "2021-04-06",
            "eol": "2024-04-01",
            "lts": True,
            "latest": "3.2.25",
        },
        {
            "cycle": "4.0",
            "releaseDate": "2021-12-07",
            "eol": "2023-04-01",
            "lts": False,
            "latest": "4.0.10",
        },
        {
            "cycle": "4.1",
            "releaseDate": "2022-08-03",
            "eol": "2023-12-01",
            "lts": False,
            "latest": "4.1.13",
        },
        {
            "cycle": "4.2",
            "releaseDate": "2023-04-03",
            "eol": "2026-04-07",
            "lts": True,
            "latest": "4.2.30",
        },
        {
            "cycle": "5.0",
            "releaseDate": "2023-12-04",
            "eol": "2025-04-02",
            "lts": False,
            "latest": "5.0.14",
        },
        {
            "cycle": "5.1",
            "releaseDate": "2024-08-07",
            "eol": "2025-12-03",
            "lts": False,
            "latest": "5.1.15",
        },
        {
            "cycle": "5.2",
            "releaseDate": "2025-04-02",
            "eol": "2028-04-30",
            "lts": True,
            "latest": "5.2.18",
        },
        {
            "cycle": "6.0",
            "releaseDate": "2025-12-03",
            "eol": "2027-04-30",
            "lts": False,
            "latest": "6.0.9",
        },
        {
            "cycle": "6.1",
            "releaseDate": "2026-08-05",
            "eol": "2027-12-31",
            "lts": False,
            "latest": "6.1.2",
        },
    ],
    "rails": [
        {"cycle": "6.0", "releaseDate": "2019-08-16", "eol": "2023-06-01", "latest": "6.0.6.1"},
        {"cycle": "6.1", "releaseDate": "2020-12-09", "eol": "2024-10-01", "latest": "6.1.7.10"},
        {"cycle": "7.0", "releaseDate": "2021-12-15", "eol": "2025-04-01", "latest": "7.0.10"},
        {"cycle": "7.1", "releaseDate": "2023-10-05", "eol": "2025-10-01", "latest": "7.1.6"},
        {"cycle": "7.2", "releaseDate": "2024-08-09", "eol": "2026-08-09", "latest": "7.2.4"},
        {"cycle": "8.0", "releaseDate": "2024-11-07", "eol": "2026-11-07", "latest": "8.0.5.1"},
        {"cycle": "8.1", "releaseDate": "2025-10-22", "eol": "2027-10-10", "latest": "8.1.4"},
    ],
    "spring-boot": [
        {
            "cycle": "2.7",
            "releaseDate": "2022-05-31",
            "eol": "2023-06-30",
            "extendedSupport": "2029-06-30",
            "latest": "2.7.18",
        },
        {
            "cycle": "3.0",
            "releaseDate": "2022-11-24",
            "eol": "2023-12-31",
            "extendedSupport": "2024-12-31",
            "latest": "3.0.13",
        },
        {
            "cycle": "3.1",
            "releaseDate": "2023-05-31",
            "eol": "2024-06-30",
            "extendedSupport": "2025-06-30",
            "latest": "3.1.12",
        },
        {
            "cycle": "3.2",
            "releaseDate": "2023-11-30",
            "eol": "2024-12-31",
            "extendedSupport": "2025-12-31",
            "latest": "3.2.12",
        },
        {
            "cycle": "3.3",
            "releaseDate": "2024-05-31",
            "eol": "2025-06-30",
            "extendedSupport": "2026-06-30",
            "latest": "3.3.13",
        },
        {
            "cycle": "3.4",
            "releaseDate": "2024-11-30",
            "eol": "2025-12-31",
            "extendedSupport": "2026-12-31",
            "latest": "3.4.13",
        },
        {
            "cycle": "3.5",
            "releaseDate": "2025-05-31",
            "eol": "2026-06-30",
            "extendedSupport": "2032-06-30",
            "latest": "3.5.16",
        },
        {
            "cycle": "4.0",
            "releaseDate": "2025-11-30",
            "eol": "2026-12-31",
            "extendedSupport": "2027-12-31",
            "latest": "4.0.9",
        },
        {
            "cycle": "4.1",
            "releaseDate": "2026-06-30",
            "eol": "2027-07-31",
            "extendedSupport": "2028-07-31",
            "latest": "4.1.2",
        },
    ],
    "python": [
        {"cycle": "3.8", "releaseDate": "2019-10-14", "eol": "2024-10-07", "latest": "3.8.20"},
        {"cycle": "3.9", "releaseDate": "2020-10-05", "eol": "2025-10-31", "latest": "3.9.25"},
        {"cycle": "3.10", "releaseDate": "2021-10-04", "eol": "2026-10-01", "latest": "3.10.22"},
        {"cycle": "3.11", "releaseDate": "2022-10-24", "eol": "2027-10-31", "latest": "3.11.17"},
        {"cycle": "3.12", "releaseDate": "2023-10-02", "eol": "2028-10-31", "latest": "3.12.15"},
        {"cycle": "3.13", "releaseDate": "2024-10-07", "eol": "2029-10-31", "latest": "3.13.17"},
        {"cycle": "3.14", "releaseDate": "2025-10-07", "eol": "2030-10-31", "latest": "3.14.9"},
        {"cycle": "3.15", "releaseDate": "2026-10-09", "eol": "2031-10-31", "latest": "3.15.1"},
    ],
    "nodejs": [
        {
            "cycle": "16",
            "releaseDate": "2021-04-20",
            "eol": "2023-09-11",
            "lts": "2021-10-26",
            "latest": "16.20.2",
        },
        {
            "cycle": "17",
            "releaseDate": "2021-10-19",
            "eol": "2022-06-01",
            "lts": False,
            "latest": "17.9.1",
        },
        {
            "cycle": "18",
            "releaseDate": "2022-04-19",
            "eol": "2025-04-30",
            "lts": "2022-10-25",
            "latest": "18.20.8",
        },
        {
            "cycle": "19",
            "releaseDate": "2022-10-18",
            "eol": "2023-06-01",
            "lts": False,
            "latest": "19.9.0",
        },
        {
            "cycle": "20",
            "releaseDate": "2023-04-18",
            "eol": "2026-04-30",
            "lts": "2023-10-24",
            "latest": "20.20.2",
        },
        {
            "cycle": "21",
            "releaseDate": "2023-10-17",
            "eol": "2024-06-01",
            "lts": False,
            "latest": "21.7.3",
        },
        {
            "cycle": "22",
            "releaseDate": "2024-04-24",
            "eol": "2027-04-30",
            "lts": "2024-10-29",
            "latest": "22.23.4",
        },
        {
            "cycle": "23",
            "releaseDate": "2024-10-16",
            "eol": "2025-06-01",
            "lts": False,
            "latest": "23.11.1",
        },
        {
            "cycle": "24",
            "releaseDate": "2025-05-06",
            "eol": "2028-04-30",
            "lts": "2025-10-28",
            "latest": "24.22.1",
        },
        {
            "cycle": "25",
            "releaseDate": "2025-10-15",
            "eol": "2026-06-01",
            "lts": False,
            "latest": "25.9.0",
        },
        {
            "cycle": "26",
            "releaseDate": "2026-05-05",
            "eol": "2029-04-30",
            "lts": "2026-10-28",
            "latest": "26.12.1",
        },
    ],
}

LABELS = {
    "django": "Django",
    "rails": "Ruby on Rails",
    "spring-boot": "Spring Boot",
    "python": "Python",
    "nodejs": "Node.js",
}
# Products whose version is a "major" cycle (Node 18) rather than "major.minor" (Django 4.2).
MAJOR_ONLY = {"nodejs"}


def _d(s: str) -> date:
    return date.fromisoformat(s)


def cache_path() -> Path:
    from ..config import settings

    return settings().context_dir / "eol-cache.json"


def catalog() -> dict[str, list[dict]]:
    """Cached refresh if present, else the built-in snapshot."""
    try:
        data = json.loads(cache_path().read_text())
        if isinstance(data, dict) and all(isinstance(v, list) for v in data.values()):
            return {**BUILTIN, **data}
    except (OSError, ValueError, ImportError):
        pass
    return BUILTIN


def refresh(products: list[str] | None = None) -> Path:
    import httpx

    out = {}
    for p in products or list(BUILTIN):
        r = httpx.get(SOURCE.format(product=p), timeout=20)
        r.raise_for_status()
        out[p] = r.json()
    path = cache_path()
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, indent=1))
    return path


def cycle_of(product: str, version: str) -> str:
    parts = version.strip().lstrip("vV").split(".")
    return parts[0] if product in MAJOR_ONLY else ".".join(parts[:2])


@dataclass(frozen=True)
class CycleStatus:
    product: str
    version: str
    cycle: str
    status: Status
    eol: str | None
    days_overdue: int  # >0 when past EOL
    days_left: int  # >0 when still supported
    latest_in_cycle: str | None
    recommended: str | None  # cycle to upgrade to
    recommended_latest: str | None
    extended_support: str | None  # commercial support end, if the vendor sells one


def _supported(row: dict, today: date) -> bool:
    return _d(row["eol"]) > today


def recommended_cycle(product: str, today: date, rows: list[dict] | None = None) -> dict | None:
    """LTS products: newest active LTS. Others: newest supported cycle released >= 180 days ago."""
    rows = rows if rows is not None else catalog().get(product, [])
    live = [r for r in rows if _supported(r, today)]
    lts = [
        r
        for r in live
        if r.get("lts") is True or (isinstance(r.get("lts"), str) and _d(r["lts"]) <= today)
    ]
    if any("lts" in r for r in rows) and lts:
        pool = lts
    else:
        pool = [r for r in live if _d(r["releaseDate"]) <= today - timedelta(days=180)] or live
    return max(pool, key=lambda r: _d(r["releaseDate"])) if pool else None


def status_for(product: str, version: str, today: date | None = None) -> CycleStatus:
    today = today or date.today()
    rows = catalog().get(product, [])
    cycle = cycle_of(product, version)
    row = next((r for r in rows if str(r["cycle"]) == cycle), None)
    rec = recommended_cycle(product, today, rows)
    if row is None:
        return CycleStatus(
            product,
            version,
            cycle,
            "unknown",
            None,
            0,
            0,
            None,
            rec and str(rec["cycle"]),
            rec and rec.get("latest"),
            None,
        )
    eol = _d(row["eol"])
    delta = (eol - today).days
    if delta <= 0:
        status: Status = "eol"
    elif delta <= EXPIRING_DAYS:
        status = "expiring"
    else:
        status = "supported"
    same = rec is not None and str(rec["cycle"]) == cycle
    return CycleStatus(
        product=product,
        version=version,
        cycle=cycle,
        status=status,
        eol=row["eol"],
        days_overdue=max(0, -delta),
        days_left=max(0, delta),
        latest_in_cycle=row.get("latest"),
        recommended=None if same or rec is None else str(rec["cycle"]),
        recommended_latest=None if same or rec is None else rec.get("latest"),
        extended_support=row.get("extendedSupport"),
    )
