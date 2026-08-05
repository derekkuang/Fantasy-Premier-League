#!/usr/bin/env python3
"""Play seasons on each projection and compare what they actually scored.

The project's accuracy numbers are all RANKING metrics. This measures the thing the product does
— buy fifteen, pick eleven, choose a captain, decide whether a transfer is worth −4 — by running
full seasons under FPL's rules and counting the points.

WHY IT DEFAULTS TO MANY STARTS AND MANY SEASONS, which is not a convenience:

  The first version of this script ran ONE start on ONE season and reported that our projection
  loses to FPL's by 4.13 points a gameweek. Across eighteen starts of the same season the same
  code says we WIN by 2.08. Across a second season it says we lose by 1.47. All three numbers are
  arithmetically correct and two of them are worthless, because the opening squad is a single
  decision whose consequences persist for the whole run — a season total is one draw from a very
  wide distribution (sd ≈ 4.3 points a gameweek between starts).

  §23 published a headline from one season and §24 had to retract it. So the defaults here are
  the honest configuration, and running narrower than that prints a warning rather than a number
  that looks like a finding.

Four policies through the IDENTICAL simulator, so every simplification (no chips, no multi-week
planning, no price-rise trading) cancels and any difference is attributable to the projection:

    ours        our structured xP
    fpl         FPL's own pre-deadline ep_next
    template    ownership — "follow the crowd", which is what most managers are
    random      noise, which is what the machinery scores with no projection at all

Usage:
    python scripts/simulate_season.py                       # 2023-24 and 2024-25, 18 starts each
    python scripts/simulate_season.py --seasons 2024-25     # one season — prints a warning
"""

from __future__ import annotations

import argparse
import pathlib
import random
import statistics as st
import sys
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpledge.eval.fpl_backtest import validate_xp
from fpledge.eval.season_sim import build_gw_pool, simulate_season
from fpledge.ingest import vaastav

POLICIES = [
    ("ours", "xp"),
    ("FPL", "fpl_xp"),
    ("template", "ownership"),
    ("random", "random"),
]
DEFAULT_SEASONS = ["2023-24", "2024-25"]
MIN_GAMEWEEKS = 12          # a run shorter than this is dominated by its opening squad


def run_season(season: str, seed: int) -> dict:
    rows = vaastav.fetch_player_gws(season)
    fixtures = vaastav.fetch_fixtures(season)
    teams = vaastav.fetch_teams(season)

    met, records = validate_xp(rows, fixtures, teams, burn_in=8, minutes_mode="recent",
                               return_records=True)
    if not met.get("baseline_clean"):
        print(f"  WARNING [{season}]: the FPL baseline is the contaminated column — see §16")

    pool = build_gw_pool(rows, records, teams)
    rng = random.Random(seed)
    for gw in pool.values():
        for p in gw.values():
            p["random"] = rng.random()

    gws = sorted(pool)
    starts = [g for g in gws if g <= gws[-1] - MIN_GAMEWEEKS]
    per: dict = defaultdict(list)
    for s in starts:
        for label, key in POLICIES:
            per[label].append(simulate_season(pool, projection=key, start_gw=s)["points_per_gw"])
    return {"season": season, "starts": starts, "per": per,
            "spearman_ours": met["played_only"]["gw_spearman_model"],
            "spearman_fpl": met["played_only"]["gw_spearman_fpl"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", nargs="+", default=DEFAULT_SEASONS)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    results = []
    for season in args.seasons:
        print(f"loading and walking forward: {season}...", flush=True)
        results.append(run_season(season, args.seed))

    print(f"\n{'season':10s} {'starts':>7s} " + "".join(f"{lbl:>10s}" for lbl, _ in POLICIES)
          + f"{'ours-FPL':>10s} {'wins':>7s}")
    diffs_all = []
    for r in results:
        per = r["per"]
        d = [a - b for a, b in zip(per["ours"], per["FPL"])]
        diffs_all.append((r["season"], d))
        cells = "".join(f"{st.mean(per[lbl]):10.2f}" for lbl, _ in POLICIES)
        print(f"{r['season']:10s} {len(r['starts']):7d} {cells}"
              f"{st.mean(d):+10.2f} {sum(x > 0 for x in d):3d}/{len(d):<3d}")

    print(f"\n{'season':10s} {'Spearman ours':>15s} {'Spearman FPL':>14s}")
    for r in results:
        print(f"{r['season']:10s} {r['spearman_ours']:15.3f} {r['spearman_fpl']:14.3f}")

    print("\n--- reading this honestly ---")
    signs = {season: (1 if st.mean(d) > 0 else -1) for season, d in diffs_all}
    pooled = [x for _s, d in diffs_all for x in d]
    sd = st.pstdev(pooled) if len(pooled) > 1 else 0.0
    print(f"pooled ours-FPL: {st.mean(pooled):+.2f}/gw   sd between starts {sd:.2f}")
    if len(results) < 2:
        print("ONE SEASON ONLY. §23 published a one-season headline and §24 retracted it. "
              "Run at least two before calling anything a finding.")
    elif len(set(signs.values())) > 1:
        print("THE SIGN FLIPS BETWEEN SEASONS. The decision-level difference is not established "
              "— see docs/HANDOFF.md §24. Ranking replicates; decisions do not.")
    else:
        print("Same sign in every season. Still check the magnitude against the start-to-start "
              f"sd of {sd:.2f} before treating it as an edge.")


if __name__ == "__main__":
    main()
