#!/usr/bin/env python3
"""Validate the xP model against realized FPL points (walk-forward, vs FPL's own xP).

Downloads vaastav historical per-GW data for a completed season, then scores model xP
against `total_points` gameweek by gameweek, with FPL's `xP` as the baseline to beat.

Usage: python scripts/validate_xp.py [season]   (default 2025-26)
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpledge.eval.fpl_backtest import validate_xp  # noqa: E402
from fpledge.ingest import vaastav  # noqa: E402

SEASON = sys.argv[1] if len(sys.argv) > 1 else "2025-26"


def _fmt(x) -> str:
    return f"{x:.3f}" if isinstance(x, float) else str(x)


def main() -> None:
    print(f"downloading vaastav {SEASON} (players + fixtures + teams)...")
    rows = vaastav.fetch_player_gws(SEASON)
    fixtures = vaastav.fetch_fixtures(SEASON)
    teams = vaastav.fetch_teams(SEASON)
    print(f"  {len(rows)} player-GWs, {len(fixtures)} fixtures. Walking forward...")

    res = validate_xp(rows, fixtures, teams, burn_in=8)
    if not res.get("n"):
        print("no scored records.")
        return

    def block(title: str, d: dict) -> None:
        print(f"\n  {title}  ({d['n']} player-GWs)        MODEL    FPL xP")
        print(f"    MAE vs actual points :  {d['mae_model']:.3f}    {d['mae_fpl']:.3f}")
        print(f"    per-GW Spearman      :  {_fmt(d['gw_spearman_model'])}    {_fmt(d['gw_spearman_fpl'])}")
        print(f"    GWs model MAE <= FPL :  {d['gws_model_mae_beats_fpl']}")

    print(f"\n=== xP VALIDATION — {SEASON} ({res['n']} player-GWs across {res['gws_scored']} GWs) ===")
    print("  (lower MAE / higher Spearman is better; FPL's own xP is the baseline to beat)")
    block("ALL players (incl. non-starters)", res["all_players"])
    block("PLAYED only (minutes>0) — the honest 'who to pick' test", res["played_only"])
    print("\n  model MAE by position (played only):")
    for pos, m in res["mae_by_position_played"].items():
        print(f"    {pos}: {m:.3f}")
    print("\n  per-GW Spearman = how well xP RANKS players by actual points within a gameweek,")
    print("  which is what matters for captaincy/transfer picks.")


if __name__ == "__main__":
    main()
