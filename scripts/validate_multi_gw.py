#!/usr/bin/env python3
"""Validate the multi-gameweek xP outlook against FPL's own xP (walk-forward).

Sums each player's model xP and FPL's xP over rolling N-GW windows and ranks them against
realized N-GW points. Answers: "if you pick on an N-week outlook, does our summed xP rank
the real N-week output as well as FPL's summed xP?" FPL's summed xP is the baseline.

Usage: python scripts/validate_multi_gw.py [season]   (default 2025-26)
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpledge.eval.fpl_backtest import validate_multi_gw, validate_xp
from fpledge.ingest import vaastav

SEASON = sys.argv[1] if len(sys.argv) > 1 else "2025-26"


def _f(x) -> str:
    return f"{x:.3f}" if isinstance(x, float) else str(x)


def main() -> None:
    print(f"downloading vaastav {SEASON} ...")
    rows = vaastav.fetch_player_gws(SEASON)
    fixtures = vaastav.fetch_fixtures(SEASON)
    teams = vaastav.fetch_teams(SEASON)
    print(f"  {len(rows)} player-GWs. Walking forward (production config)...")

    _, records = validate_xp(
        rows, fixtures, teams, burn_in=8, minutes_mode="recent",
        bonus_mode="rate", return_records=True,
    )

    print(f"\n=== MULTI-GW xP vs FPL — {SEASON} (played only) ===")
    print("  window | Spearman model  FPL | MAE model  FPL | windows n")
    for w in (1, 3, 5):
        r = validate_multi_gw(records, window=w)
        print(
            f"  {w:>4}GW | {_f(r['gw_spearman_model']):>13}  {_f(r['gw_spearman_fpl']):>4} "
            f"| {_f(r['mae_model']):>8}  {_f(r['mae_fpl']):>4} | {r['windows_scored']} win, {r['n']} pts"
        )
    print("\n  (higher Spearman / lower MAE better; FPL's own xP summed over the window is the baseline)")


if __name__ == "__main__":
    main()
