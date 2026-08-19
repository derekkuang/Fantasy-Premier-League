"""Immutable, timestamped raw landing zone.

Local paths mirror an S3 key convention so this swaps to s3fs/boto3 later without
changing callers:

    data/raw/source=fpl_api/endpoint=bootstrap/season=2025-26/gw=03/
             ingest_ts=2026-07-24T06-00-05Z/data.json.gz

Because every object is stamped with ingest time and never overwritten, the raw
zone is replayable and leakage-safe by construction.
"""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path

from .. import config


def utc_stamp() -> str:
    """Filesystem-safe UTC timestamp, e.g. 2026-07-24T06-00-05Z."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")


def land(
    payload,
    source: str,
    endpoint: str,
    season: str | None = None,
    gameweek: int | None = None,
    ingest_ts: str | None = None,
) -> Path:
    """Write `payload` (JSON-serialisable) to the partitioned raw zone; return path."""
    season = season or config.SEASON
    ts = ingest_ts or utc_stamp()

    parts = [f"source={source}", f"endpoint={endpoint}", f"season={season}"]
    if gameweek is not None:
        parts.append(f"gw={int(gameweek):02d}")
    parts.append(f"ingest_ts={ts}")

    out_dir = config.RAW_DIR.joinpath(*parts)
    out_dir.mkdir(parents=True, exist_ok=True)
    fp = out_dir / "data.json.gz"
    with gzip.open(fp, "wt", encoding="utf-8") as f:
        json.dump(payload, f)
    return fp
