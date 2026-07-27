#!/usr/bin/env python3
"""Print the expected-points (xP) table for the upcoming gameweek.

Thin wrapper over fpledge.gw.records_for_gw (load -> Dixon-Coles -> minutes-aware shares ->
clean sheets/saves/bonus/defensive-contribution -> rank-relative value). Shows xP, price,
ownership, differential value, and a safe (max-xP) vs differential (floored) captain.

Usage: python scripts/build_xp.py
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpledge import config  # noqa: E402
from fpledge.gw import records_for_gw  # noqa: E402
from fpledge.models import rank  # noqa: E402

UPCOMING_GW = 1


def main() -> None:
    out = records_for_gw(UPCOMING_GW)
    if out is None:
        print("no player_season data — run scripts/pull_player_history.py first.")
        return
    records, coverage, fpl_teams, skipped = (
        out["records"], out["coverage"], out["fpl_teams"], out["skipped"]
    )
    reliable = sorted((r for r in records if not r["low_cov"]), key=lambda r: r["xp"], reverse=True)

    print(f"\n=== xP TABLE — GW{UPCOMING_GW} {config.SEASON}  (top 20, reliable-data teams) ===")
    print(f"{'xP':>5} {'diff':>5} {'£':>4} {'own%':>5}  {'player':<15}{'pos':<4}{'team':<16}")
    for r in reliable[:20]:
        print(f"{r['xp']:5.2f} {r['diff_value']:5.2f} {r['price']:4.1f} {r['ownership']:5.1f}  "
              f"{r['web_name']:<15}{r['position']:<4}{(r['team_name'] or '?'):<16}")

    if reliable:
        safe = reliable[0]
        di = rank.differential_captain_index(
            [r["xp"] for r in reliable], [r["eo"] for r in reliable], alpha=0.8
        )
        diffcap = reliable[di] if di is not None else None
        print(f"\n  captain — safe (max xP)      : {safe['web_name']} ({safe['team_name']}) — "
              f"{safe['xp']:.2f} xP, {safe['ownership']:.1f}% owned")
        if diffcap is not None and diffcap["web_name"] != safe["web_name"]:
            print(f"  captain — differential (hi-var, xP within 80% of best): {diffcap['web_name']} "
                  f"({diffcap['team_name']}) — {diffcap['xp']:.2f} xP, {diffcap['ownership']:.1f}% owned")
        else:
            print("  captain — differential       : none clears the xP floor; safe pick is the value pick too")

    low_teams = sorted(t for t, mins in coverage.items() if mins < 9000)
    if low_teams:
        print(f"  excluded low-data teams: {[fpl_teams.get(t, '?') for t in low_teams]}")
    if skipped:
        print(f"  skipped {len(skipped)} fixtures (promoted/unknown to engine): {skipped}")
    print("\n  cols: xP = expected points | diff = rank-upside if owned = xP*(1-EO) | £ = price")
    print("  caveats: EO uses overall ownership; near-deadline team news not yet ingested;")
    print("  new signings use prior-club output. First cut, not gospel.")


if __name__ == "__main__":
    main()
