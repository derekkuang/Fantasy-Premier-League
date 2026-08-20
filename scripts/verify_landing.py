#!/usr/bin/env python3
"""Prove the configured landing backend actually works, before trusting a capture to it.

WHY THIS EXISTS. The captures collect data that cannot be bought back at any price, and the
first time a new backend is exercised should not be at 06:00 on a deadline morning, unattended,
on the only run that mattered. This writes a throwaway object, reads it back, compares it byte
for byte, and lists it — the same four operations every capture depends on.

    python scripts/verify_landing.py                      # whatever is configured
    FPLEDGE_RAW_URI=s3://bucket/raw python scripts/verify_landing.py

It writes under `source=_verify`, which no real capture uses, so it can never collide with or be
mistaken for real data. Local runs clean up after themselves; S3 objects are left in place
deliberately — deleting is a permission this tool should not need, and one stray tiny object is
a much smaller problem than a verifier that can delete things in the raw zone.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpledge import config
from fpledge.ingest import landing


def main() -> None:
    uri = (config.RAW_URI or "").strip()
    backend = landing.backend()
    where = uri if uri else f"local disk ({config.RAW_DIR})"
    print(f"backend: {type(backend).__name__} -> {where}\n")

    stamp = "0000-00-00T00-00-00Z"          # fixed, so repeat runs overwrite the same probe
    payload = {"probe": True, "note": "written by scripts/verify_landing.py"}

    print("1. write   ", end="", flush=True)
    locator = landing.land(payload, source="_verify", endpoint="probe", season="_test",
                           ingest_ts=stamp)
    print(f"ok  -> {locator}")

    print("2. exists  ", end="", flush=True)
    if not landing.exists(locator):
        raise SystemExit("FAIL: wrote an object the backend then reported as absent. This is the "
                         "failure that makes a capture look successful and lose the data.")
    print("ok")

    print("3. read    ", end="", flush=True)
    got = landing.read_json(locator)
    if got != payload:
        raise SystemExit(f"FAIL: round-trip mismatch.\n  wrote {payload}\n  read  {got}")
    print("ok  (round-trips byte for byte)")

    print("4. list    ", end="", flush=True)
    found = landing.list_partitions("_verify", "probe", "_test")
    if locator not in found:
        raise SystemExit(f"FAIL: the object exists but listing did not return it.\n"
                         f"  listing found {len(found)}: {found[:3]}\n"
                         f"  `latest_raw` reads the LAST entry of this list, so a backend that "
                         f"cannot list is one that silently serves stale data.")
    print(f"ok  ({len(found)} object(s) under the probe prefix)")

    if not uri:
        pathlib.Path(locator).unlink(missing_ok=True)
        print("\ncleaned up the local probe file")
    else:
        print(f"\nleft the probe object in place: {locator}")
        print("(delete it by hand if you want the bucket pristine — this tool has no delete)")

    print("\nall four operations passed — this backend is safe to point a capture at")


if __name__ == "__main__":
    main()
