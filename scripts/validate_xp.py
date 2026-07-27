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

    print(f"\n=== xP VALIDATION — {SEASON} (GWs 9-38, {res['n']} player-GWs scored) ===")
    print("                       MODEL     FPL xP   (baseline to beat)")
    print(f"  MAE vs actual pts :  {res['mae_model']:.3f}    {res['mae_fpl']:.3f}")
    print(f"  Spearman (overall):  {res['spearman_model']:.3f}    {res['spearman_fpl']:.3f}")
    print(f"  Spearman (per-GW) :  {_fmt(res['gw_spearman_model'])}    {_fmt(res['gw_spearman_fpl'])}")
    print(f"  GWs model MAE <= FPL MAE: {res['gws_model_mae_beats_fpl']}")
    print("\n  model MAE by position:")
    for pos, m in res["mae_by_position"].items():
        print(f"    {pos}: {m:.3f}")
    lower = "MODEL" if res["mae_model"] < res["mae_fpl"] else "FPL"
    print(f"\n  read: lower MAE / higher Spearman is better. {lower} has lower MAE here.")
    print("  Spearman ~ how well xP RANKS players by actual points (what matters for picks).")


if __name__ == "__main__":
    main()
