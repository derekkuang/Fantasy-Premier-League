#!/usr/bin/env python3
"""Precompute the serving artifact the API reads (per gameweek).

Runs the engine fit once and writes data/serving/gw{gw}.json (xP records + fixture ticker).
Schedule this weekly in production; the API only ever reads its output.

IT EXITS NON-ZERO ON A DEGRADED FIT, and that is the entire point of the health check below.
The failure mode this guards against is not a crash. A dropped Football-Data season used to
print `warn:`, exit 0, and leave the engine fitted on less history — `fallback_fixtures` creeps
from 2 to 4, every projection gets slightly worse, and the site serves it happily for weeks
because nothing ever broke. docs/HANDOFF.md §4 has called this "the one thing that will silently
rot a deployed site" since 2026-08-03.

A scheduled run must therefore fail LOUDLY: the artifact is written either way (so you can
inspect it), but a non-zero exit stops a cron from treating a degraded refresh as a success.
`--allow-degraded` publishes anyway, for when you know why and mean it.

Usage: python scripts/precompute.py [gw] [horizon] [--allow-degraded]
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpledge.api.precompute import health_check, run


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    allow_degraded = "--allow-degraded" in sys.argv
    gw = int(args[0]) if args else 1
    horizon = int(args[1]) if len(args) > 1 else 8
    res = run(gw, horizon=horizon)
    m = res["meta"]
    print(f"wrote {res['path']}")
    print(
        f"  gw{m['gw']}  horizon={m['horizon']}  model={m['model_ver']}  "
        f"run_ts={m['run_ts']}  records={m['n_records']}  "
        f"fallback_fixtures={m['fallback_fixtures']}"
    )
    src = m.get("source") or {}
    if src:
        print(f"  sources: {len(src.get('loaded', []))}/{len(src.get('requested', []))} seasons, "
              f"{src.get('n_matches', 0)} matches")

    problems = health_check(m)
    if not problems:
        print("  health: OK")
        return
    print("\nDEGRADED — this artifact should not be published:")
    for pr in problems:
        print(f"  ! {pr}")
    if allow_degraded:
        print("\n--allow-degraded set; publishing anyway.")
        return
    print("\nExiting non-zero so a scheduler does not record this as a success.")
    print("Re-run, or pass --allow-degraded if you know why and mean it.")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
