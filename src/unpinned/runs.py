"""runs/<id>/ layout helpers."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from .config import settings


def new_run_id(kind: str) -> str:
    return f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{kind}-{uuid.uuid4().hex[:8]}"


def run_path(run_id: str, base: Path | None = None) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", run_id):
        raise ValueError("invalid run ID")
    root = (base or settings().runs_dir).resolve()
    path = root / run_id
    if not path.resolve().is_relative_to(root):
        raise ValueError("run directory escapes the configured root")
    return path


def run_dir(run_id: str, base: Path | None = None) -> Path:
    d = run_path(run_id, base)
    d.mkdir(parents=True, exist_ok=True)
    return d


def run_file(run_id: str, name: str) -> Path:
    directory = run_path(run_id)
    if Path(name).name != name or name in {".", ".."}:
        raise ValueError("invalid artifact filename")
    path = directory / name
    if not path.resolve().is_relative_to(directory.resolve()):
        raise ValueError("artifact escapes the run directory")
    return path


def save_json(path: Path, obj: BaseModel | dict | list) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = obj.model_dump(mode="json") if isinstance(obj, BaseModel) else obj
    path.write_text(json.dumps(data, indent=2, sort_keys=True))
    return path


def save_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path
