#!/usr/bin/env python3
"""Pick the optimal FPL squad + starting XI + captain for the upcoming gameweek.

Feeds the GW xP records into the two-level ILP (fpledge.models.optimizer): the best legal
15 (budget, quotas, <=3 per club) AND the best XI + captain within it (only the XI scores).

Usage: python scripts/build_squad.py
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpledge import config  # noqa: E402
from fpledge.gw import records_for_gw  # noqa: E402
from fpledge.models.optimizer import BUDGET, optimize_squad  # noqa: E402

UPCOMING_GW = 1
_POS_ORDER = {"GK": 0, "DEF": 1, "MID": 2, "FWD": 3}


def main() -> None:
    out = records_for_gw(UPCOMING_GW)
    if out is None:
        print("no player_season data — run scripts/pull_player_history.py first.")
        return

    pool = [
        {
            "id": r["element_id"], "name": r["web_name"], "position": r["position"],
            "price": r["price"], "team_id": r["team_id"], "team_name": r["team_name"], "xp": r["xp"],
        }
        for r in out["records"]
        if not r["low_cov"] and r["price"]
    ]
    print(f"optimising over {len(pool)} players (reliable-data teams)...")
    res = optimize_squad(pool, budget=BUDGET)
    by_id = {p["id"]: p for p in pool}

    def show(ids: list, label: str) -> None:
        print(f"\n{label}:")
        for pid in sorted(ids, key=lambda i: (_POS_ORDER[by_id[i]["position"]], -by_id[i]["xp"])):
            p = by_id[pid]
            cap = "  (C)" if pid == res["captain"] else ""
            print(f"  {p['position']:<4}{p['name']:<15}{(p['team_name'] or '?'):<14}"
                  f"£{p['price']:>4.1f}  {p['xp']:5.2f} xP{cap}")

    print(f"\n=== OPTIMAL SQUAD — GW{UPCOMING_GW} {config.SEASON} ===")
    print(f"cost £{res['cost']:.1f}m / {BUDGET:.0f}m   |   starting-XI xP {res['xi_xp']:.1f}   "
          f"total (captain doubled) {res['total_xp']:.1f}")
    show(res["starting_xi"], "STARTING XI")
    show(res["bench"], "BENCH (does not score unless auto-subbed)")
    cap = by_id[res["captain"]]
    print(f"\ncaptain: {cap['name']} ({cap['team_name']}) — {cap['xp']:.2f} xP, doubled")
    print("\n  note: single-gameweek optimisation over reliable-data teams; promoted teams and")
    print("  fixtures vs unknown opponents are excluded. Not yet multi-GW / wildcard-horizon.")


if __name__ == "__main__":
    main()
