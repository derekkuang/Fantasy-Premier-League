#!/usr/bin/env python3
"""Play a season on each projection and compare what they actually scored.

The project's accuracy numbers are all RANKING metrics. This measures the thing the product
does — buy fifteen, pick eleven, choose a captain, decide whether a transfer is worth −4 — by
running a full season under FPL's rules and counting the points.

Four policies through the IDENTICAL simulator, so every simplification (no chips, no multi-week
planning, no price-rise trading) cancels and the difference is attributable to the projection:

    ours        our structured xP
    fpl         FPL's own pre-deadline ep_next
    template    ownership — "follow the crowd", which is what most managers are
    random      noise, which is what the machinery scores with no projection at all

Usage: python scripts/simulate_season.py [season] [--xg] [--bootstrap N]
"""

from __future__ import annotations

import argparse
import pathlib
import random
import statistics as st
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpledge.eval.fpl_backtest import validate_xp
from fpledge.eval.season_sim import build_gw_pool, simulate_season
from fpledge.ingest import vaastav

POLICIES = [
    ("ours", "xp", "our structured xP"),
    ("fpl", "fpl_xp", "FPL's pre-deadline ep_next"),
    ("template", "ownership", "follow the crowd (ownership)"),
    ("random", "random", "noise — the machinery with no projection"),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("season", nargs="?", default="2024-25")
    ap.add_argument("--bootstrap", type=int, default=2000,
                    help="resamples for the gameweek-level confidence interval")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    print(f"loading {args.season}...", flush=True)
    rows = vaastav.fetch_player_gws(args.season)
    fixtures = vaastav.fetch_fixtures(args.season)
    teams = vaastav.fetch_teams(args.season)

    print("walking forward (point-in-time projections)...", flush=True)
    met, records = validate_xp(rows, fixtures, teams, burn_in=8, minutes_mode="recent",
                               return_records=True)
    if not met.get("baseline_clean"):
        print("WARNING: the FPL baseline is the contaminated column — see docs/HANDOFF.md §16")

    pool = build_gw_pool(rows, records, teams)
    rng = random.Random(args.seed)
    for gw in pool.values():
        for p in gw.values():
            p["random"] = rng.random()

    gws = sorted(pool)
    print(f"{len(gws)} gameweeks (GW{gws[0]}..GW{gws[-1]}), "
          f"{sum(len(v) for v in pool.values())} player-gameweeks\n")

    results = {}
    for name, key, label in POLICIES:
        r = simulate_season(pool, projection=key)
        results[name] = r
        print(f"{label:34s} {r['total_points']:6.0f} pts  "
              f"({r['points_per_gw']:5.2f}/gw, {r['total_transfers']:3d} transfers, "
              f"{r['total_hits']} hits)")

    base = results["ours"]
    print(f"\n{'':34s} {'total':>6s} {'/gw':>7s} {'captain':>8s} {'bench':>7s}")
    for name, _key, label in POLICIES:
        r = results[name]
        print(f"{label:34s} {r['total_points']:6.0f} {r['points_per_gw']:7.2f} "
              f"{r['captain_points']:8d} {r['bench_points']:7d}")

    # --- is the gap real, or is it one season of luck? ---------------------------------- #
    print("\n=== ours vs each baseline, paired by gameweek ===")
    ours_gw = {h["gw"]: h["points"] for h in base["history"] if "raw_points" in h}
    for name, _key, label in POLICIES:
        if name == "ours":
            continue
        other = {h["gw"]: h["points"] for h in results[name]["history"] if "raw_points" in h}
        shared = sorted(set(ours_gw) & set(other))
        diffs = [ours_gw[g] - other[g] for g in shared]
        if not diffs:
            continue
        rng2 = random.Random(args.seed)
        boots = [
            st.mean(rng2.choices(diffs, k=len(diffs)))
            for _ in range(args.bootstrap)
        ]
        boots.sort()
        lo = boots[int(0.025 * len(boots))]
        hi = boots[int(0.975 * len(boots))]
        wins = sum(d > 0 for d in diffs)
        print(f"  vs {label:32s} {st.mean(diffs):+6.2f} pts/gw   "
              f"95% CI [{lo:+.2f}, {hi:+.2f}]   won {wins}/{len(diffs)} gameweeks")

    print("\nSKILL vs LUCK: the interval above is over GAMEWEEKS within one season. It answers")
    print("'is this gap bigger than week-to-week noise', not 'would it recur next season' —")
    print("that needs more seasons, and one season is one sample however many times it is")
    print("resampled.")


if __name__ == "__main__":
    main()
