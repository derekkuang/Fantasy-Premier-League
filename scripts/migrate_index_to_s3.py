#!/usr/bin/env python3
"""One-time: publish the full capture-index history to S3, with locators a Lambda can resolve.

THE GAP THIS CLOSES. The captures now run in the cloud and read their history from S3 — but the
history's index rows carry LOCAL locators (`/Users/.../data/raw/...`), written back when the
laptop was the only place captures ran. On Lambda those paths do not exist, so every pre-cloud
capture would count as missing: `load_corpus()` would shrink to cloud-era items only, the digest
would quietly lose weeks of context, and the only symptom would be a WARNING line in a log
nobody reads.

The mapping is mechanical because the local layout mirrors the S3 key convention by design
(see `ingest.landing`): `<DATA_DIR>/raw/<key>` -> `s3://<bucket>/raw/<key>`. The data objects
themselves are already in S3 (`aws s3 sync` — run that FIRST); this rewrites the index rows
that point at them and lands each as an object under `source=_index/`, exactly as a cloud
capture would have written it. Rows already carrying `s3://` locators pass through unchanged,
so re-running is safe (same ingest_ts -> same key -> idempotent overwrite).

    FPLEDGE_RAW_URI=s3://fpledge-data-546712138633/raw python scripts/migrate_index_to_s3.py
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpledge import config
from fpledge.ingest import capture_index, landing


def rewrite(locator: str, local_prefix: str, s3_prefix: str) -> str:
    if locator.startswith(local_prefix):
        return s3_prefix + locator[len(local_prefix):]
    return locator


def main() -> None:
    uri = (config.RAW_URI or "").strip()
    if not uri.startswith("s3://"):
        raise SystemExit("FPLEDGE_RAW_URI must be an s3:// URI — this script publishes TO S3")

    local_prefix = str(config.RAW_DIR) + "/"
    s3_prefix = uri.rstrip("/") + "/"
    print(f"rewriting {local_prefix}  ->  {s3_prefix}\n")

    for kind in (capture_index.NEWS, capture_index.SNAPSHOT, capture_index.PROPS):
        rows = capture_index.entries(kind)      # merges legacy JSONL + anything already landed
        if not rows:
            print(f"{kind:<9} nothing to migrate")
            continue
        migrated = unresolvable = 0
        for row in rows:
            out = dict(row)
            if "path" in out:
                out["path"] = rewrite(out["path"], local_prefix, s3_prefix)
            if "paths" in out:
                out["paths"] = [rewrite(p, local_prefix, s3_prefix) for p in out["paths"]]
            # Refuse to publish an index row whose objects are not actually in S3 — an index
            # entry pointing at nothing recreates the exact silent shrinkage this fixes.
            locators = ([out["path"]] if "path" in out else []) + list(out.get("paths", []))
            if not all(landing.exists(loc) for loc in locators if loc):
                unresolvable += 1
                print(f"  SKIP {kind} {row.get('ingest_ts')}: object(s) not in S3 — "
                      "run `aws s3 sync data/raw s3://.../raw` first")
                continue
            capture_index.record(kind, out, ingest_ts=row.get("ingest_ts"))
            migrated += 1
        print(f"{kind:<9} {migrated} rows published to S3"
              + (f", {unresolvable} SKIPPED (missing objects)" if unresolvable else ""))


if __name__ == "__main__":
    main()
