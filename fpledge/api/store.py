"""Serving store: one self-contained JSON artifact per gameweek.

v1 is deliberately infra-free — a JSON file the precompute job writes and the API only
reads. Swap `write_gw`/`read_gw` for a Postgres-backed pair in Phase 2 without touching
the endpoints. Writes are atomic (temp file + os.replace) so a reader never sees a
half-written file. Override the directory with FPLEDGE_SERVING_DIR (used by tests).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .. import config


def serving_dir() -> Path:
    return Path(os.environ.get("FPLEDGE_SERVING_DIR", config.DATA_DIR / "serving"))


def _path(gw: int) -> Path:
    return serving_dir() / f"gw{gw}.json"


def write_gw(gw: int, payload: dict) -> Path:
    """Atomically write the serving artifact for a gameweek; return its path."""
    d = serving_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = _path(gw)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")))
    os.replace(tmp, path)  # atomic on POSIX
    return path


def read_gw(gw: int) -> dict | None:
    """Read the serving artifact for a gameweek, or None if it hasn't been precomputed."""
    path = _path(gw)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def available_gws() -> list[int]:
    """Gameweeks that have a precomputed artifact, ascending."""
    d = serving_dir()
    if not d.exists():
        return []
    gws = []
    for p in d.glob("gw*.json"):
        try:
            gws.append(int(p.stem[2:]))
        except ValueError:
            continue
    return sorted(gws)
