#!/usr/bin/env python3
"""Fixture ticker — a true FDR grid (from the engine's expected goals) for the next N GWs.

Usage: python scripts/fixture_ticker.py
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpledge import config
from fpledge.fdr import fixture_ticker
from fpledge.ingest import footballdata
from fpledge.models.dixon_coles import DixonColesModel
from fpledge.models.teammap import build_team_map
from fpledge.storage import duck

SEASONS = ["2324", "2425", "2526"]
START_GW = 1
HORIZON = 5


def main() -> None:
    con = duck.connect()
    duck.init_schema(con)
    fpl_teams = {
        t: n for t, n in con.execute(
            "SELECT team_id, name FROM teams WHERE season = ?", [config.SEASON]
        ).fetchall()
    }
    fixtures = [
        {"gw": gw, "home_id": h, "away_id": a}
        for gw, h, a in con.execute(
            "SELECT gw, home_id, away_id FROM fixtures WHERE season = ? AND gw >= ? AND gw < ?",
            [config.SEASON, START_GW, START_GW + HORIZON],
        ).fetchall()
    ]
    con.close()
    if not fpl_teams:
        print("no teams — run scripts/build_db.py first.")
        return

    matches = footballdata.load_seasons(SEASONS)
    engine = DixonColesModel(180).fit(matches)
    fd = sorted({m["home"] for m in matches} | {m["away"] for m in matches})
    tmap = build_team_map(list(fpl_teams.values()), fd)
    ticker = fixture_ticker(engine, fixtures, fpl_teams, tmap, START_GW, HORIZON)

    def attack_ease(fxs):
        return sum(f["lam_for"] for f in fxs)

    gws = list(range(START_GW, START_GW + HORIZON))
    print(f"\n=== FIXTURE TICKER — GW{gws[0]}-{gws[-1]} {config.SEASON} (true FDR from engine λ) ===")
    header = "  " + f"{'team':<16}" + "  ".join(f"{'GW'+str(g):<9}" for g in gws)
    print(header)
    for tid, fxs in sorted(ticker.items(), key=lambda kv: attack_ease(kv[1]), reverse=True):
        by_gw = {f["gw"]: f for f in fxs}
        cells = []
        for g in gws:
            f = by_gw.get(g)
            cells.append(
                f"{(f['opp'] or '?')[:3].upper()}{'H' if f['home'] else 'A'}·{f['attack_fdr']}"
                if f else "  -"
            )
        print("  " + f"{fpl_teams[tid]:<16}" + "  ".join(f"{c:<9}" for c in cells))

    print("\n  cell = opponent(H/A)·attack-FDR (1=easy … 5=hard); sorted by easiest attack run.")
    best_cs = sorted(ticker.items(), key=lambda kv: sum(f["lam_against"] for f in kv[1]) / len(kv[1]))
    print("  best clean-sheet runs (lowest avg expected goals-against):")
    for tid, fxs in best_cs[:5]:
        print(f"    {fpl_teams[tid]:<16} avg λ-against {sum(f['lam_against'] for f in fxs) / len(fxs):.2f}")


if __name__ == "__main__":
    main()
