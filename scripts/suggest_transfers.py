#!/usr/bin/env python3
"""Transfer suggester demo — best single transfer by xP gain, net of the -4 hit.

Builds the optimal squad, then DEGRADES it (sells its best outfielder for the cheapest
same-position spare, banking the difference) so there's an obvious move, and asks the
suggester for the best transfers — free, and on a hit. Works on any real squad too.

Usage: python scripts/suggest_transfers.py
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpledge.gw import records_for_gw
from fpledge.models.optimizer import BUDGET, optimize_squad
from fpledge.transfers import suggest_transfers


def main() -> None:
    out = records_for_gw(1)
    if out is None:
        print("no player_season data — run scripts/pull_player_history.py first.")
        return

    pool = [
        {"id": r["element_id"], "name": r["web_name"], "position": r["position"],
         "price": r["price"], "team_id": r["team_id"], "team_name": r["team_name"], "xp": r["xp"]}
        for r in out["records"] if not r["low_cov"] and r["price"]
    ]
    by_id = {p["id"]: p for p in pool}
    squad = list(optimize_squad(pool, budget=BUDGET)["squad"])

    # Degrade: sell the best outfielder for the cheapest same-position spare.
    best_out = max((by_id[i] for i in squad if by_id[i]["position"] != "GK"), key=lambda p: p["xp"])
    spare = min(
        (p for p in pool if p["position"] == best_out["position"] and p["id"] not in squad),
        key=lambda p: p["price"],
    )
    degraded = [i for i in squad if i != best_out["id"]] + [spare["id"]]
    bank = round(best_out["price"] - spare["price"], 1)
    print(f"demo squad = optimal, but {best_out['name']} (£{best_out['price']}) sold for "
          f"{spare['name']} (£{spare['price']}) — £{bank}m in the bank\n")

    for free in (1, 0):
        header = "free transfer" if free else "on a -4 hit"
        print(f"=== best transfers ({header}) ===")
        for s in suggest_transfers(degraded, by_id, bank=bank, free_transfers=free, top=5):
            print(f"  OUT {s['out']['name']:<14} → IN {s['in']['name']:<14} "
                  f"(£{s['cost']:+.1f})  +{s['gain']:.2f} xP  →  net {s['net']:+.2f}")
        print()


if __name__ == "__main__":
    main()
