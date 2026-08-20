"""The capture index: what ran, when, and what it produced — durable, and append-free.

WHAT THIS REPLACES. Both captures appended a line to a local JSONL:

    with INDEX.open("a") as fh:
        fh.write(json.dumps(row) + "\\n")

That is exactly right on one machine and impossible anywhere else. A Lambda's filesystem is
read-only apart from /tmp, and /tmp is discarded when the execution environment dies — so a
capture running on a scheduler would do all its work, write its objects, and then lose the only
record that it happened. Every reader keys off that index, so the data would be present in the
raw zone and invisible to the project.

WHY ONE OBJECT PER CAPTURE, RATHER THAN A JSONL IN S3. Appending to an object is not an
operation S3 has: you read it, add a line, and write the whole thing back. Two captures
overlapping — a retry, a manual run beside a scheduled one, two Lambdas the scheduler
double-fired — and the second silently erases the first's entry. Writing one immutable object
per capture has no such window, and it is the same partitioned shape the raw zone already uses,
so it needs no new storage primitive.

THE LEGACY JSONL IS STILL READ. Thirteen news captures and a snapshot exist only in the local
files, and history that stops resolving is the failure this whole layer exists to avoid. Reads
merge both sources; writes only ever go to the new one.
"""

from __future__ import annotations

import json
import pathlib
from concurrent.futures import ThreadPoolExecutor

from .. import config
from . import landing

# Kinds are the capture families. The value is also the legacy filename stem, so the two stay
# tied together rather than drifting into a lookup nobody maintains.
NEWS = "news"
SNAPSHOT = "snapshot"
PROPS = "props"

_INDEX_SOURCE = "_index"          # a source no real capture uses, so it cannot collide


def legacy_path(kind: str) -> pathlib.Path:
    """Where this kind's index lived before it moved to object storage."""
    return config.DATA_DIR / "raw" / f"{kind}_index.jsonl"


def record(kind: str, row: dict, ingest_ts: str | None = None) -> str:
    """Persist one capture's index entry; return its locator.

    Goes through `landing`, so it lands wherever the raw zone is configured — local disk in
    development, S3 on a scheduler — with no branch here.
    """
    ts = ingest_ts or row.get("ingest_ts") or landing.utc_stamp()
    return landing.land(row, source=_INDEX_SOURCE, endpoint=kind, ingest_ts=ts)


def _legacy_entries(kind: str) -> list[dict]:
    path = legacy_path(kind)
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def _landed_entries(kind: str) -> list[dict]:
    locators = landing.list_partitions(_INDEX_SOURCE, kind)
    if not locators:
        return []
    # One GET per entry, so fetch them concurrently — a season of thrice-daily captures is
    # ~1,000 objects and doing that serially against S3 turns a read into a coffee break.
    with ThreadPoolExecutor(max_workers=16) as pool:
        return list(pool.map(landing.read_json, locators))


def entries(kind: str) -> list[dict]:
    """Every capture of this kind, oldest first, from both the legacy file and object storage.

    Deduped on `ingest_ts`: a capture migrated into object storage should not also count as a
    separate run just because its old line is still in the JSONL. The landed copy wins, being
    the one a re-run would update.
    """
    merged: dict[str, dict] = {}
    for row in _legacy_entries(kind):
        key = row.get("ingest_ts") or row.get("captured_at") or json.dumps(row, sort_keys=True)
        merged[key] = row
    for row in _landed_entries(kind):
        key = row.get("ingest_ts") or row.get("captured_at") or json.dumps(row, sort_keys=True)
        merged[key] = row
    return [merged[k] for k in sorted(merged)]
