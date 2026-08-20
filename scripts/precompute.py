#!/usr/bin/env python3
"""Precompute the serving artifact the API reads (per gameweek).

Runs the engine fit once, GATES the result, and only then publishes to wherever the serving
store points (local disk, or the live S3 when FPLEDGE_SERVING_URI is set).

THE GATE RUNS BEFORE THE PUBLISH, and the order is the point. An earlier version wrote the
artifact first and health-checked after — correct when "written" meant a local file a human
would inspect, and silently wrong from the moment the store began publishing straight to the
S3 the live API serves: "written either way so you can inspect it" had become "served to users
either way". Now a degraded artifact never reaches the store; it is dumped beside the build
outputs for inspection instead.

Two gates, catching different failures (fpledge.api.precompute):
  health_check   the fit's own report of its INPUTS — dropped source seasons, broken team
                 mapping, too few records. §4's "the one thing that will silently rot a
                 deployed site".
  publish_gate   the new artifact against the one CURRENTLY SERVED — a degenerate fit whose
                 inputs all looked fine (projections collapsed, half the players vanished).
                 Wide thresholds on purpose: it trips on "grossly wrong", never on "different".

Usage:
    python scripts/precompute.py                       # NEXT gameweek (from the bootstrap), horizon 8
    python scripts/precompute.py 3 8                   # explicit gameweek + horizon
    python scripts/precompute.py --allow-degraded      # publish anyway, when you know why
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpledge.api.precompute import next_gameweek, run


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    args = [a for a in argv if not a.startswith("--")]
    allow_degraded = "--allow-degraded" in argv

    # No positional argument means "the next gameweek", resolved from the landed bootstrap. A
    # scheduler must never pass a literal number — it goes stale the moment a gameweek
    # completes, and the site quietly serves last week's projections as current.
    gw = int(args[0]) if args else next_gameweek()
    horizon = int(args[1]) if len(args) > 1 else 8

    res = run(gw, horizon=horizon, allow_degraded=allow_degraded)
    m = res["meta"]
    print(
        f"gw{m['gw']}  horizon={m['horizon']}  model={m['model_ver']}  "
        f"run_ts={m['run_ts']}  records={m['n_records']}  "
        f"fallback_fixtures={m['fallback_fixtures']}"
    )
    src = m.get("source") or {}
    if src:
        print(f"  sources: {len(src.get('loaded', []))}/{len(src.get('requested', []))} seasons, "
              f"{src.get('n_matches', 0)} matches")

    if res["published"]:
        if res["problems"]:
            print("published DESPITE problems (--allow-degraded):")
            for pr in res["problems"]:
                print(f"  ! {pr}")
        else:
            print("  gates: OK")
        print(f"published -> {res['path']}")
        return

    # Blocked. The artifact goes somewhere a human can inspect — NEVER the serving store.
    dump = pathlib.Path("build") / f"blocked-gw{gw}.json"
    dump.parent.mkdir(parents=True, exist_ok=True)
    dump.write_text(json.dumps(res["payload"], separators=(",", ":")))
    print("\nBLOCKED — this artifact was NOT published:")
    for pr in res["problems"]:
        print(f"  ! {pr}")
    print(f"\nthe blocked artifact is at {dump} for inspection.")
    print("Re-run, or pass --allow-degraded if you know why and mean it.")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
