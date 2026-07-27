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

    print("  A/B: season-average vs recency-weighted minutes (two walk-forwards)...")
    season = validate_xp(rows, fixtures, teams, burn_in=8, minutes_mode="season")
    recent = validate_xp(rows, fixtures, teams, burn_in=8, minutes_mode="recent")
    if not season.get("n"):
        print("no scored records.")
        return

    def ab(label: str, s_val, r_val, fpl_val) -> None:
        print(f"    {label:20}  season {_fmt(s_val)}   recent {_fmt(r_val)}   |  FPL {_fmt(fpl_val)}")

    print(f"\n=== xP VALIDATION A/B — {SEASON} ({season['n']} player-GWs, {season['gws_scored']} GWs) ===")
    print("  (higher Spearman / lower MAE is better; FPL's own xP is the baseline to beat)")
    for subset, title in (("played_only", "PLAYED only (who to pick)"), ("all_players", "ALL players")):
        s, r = season[subset], recent[subset]
        print(f"\n  {title}  ({s['n']} player-GWs):")
        ab("per-GW Spearman", s["gw_spearman_model"], r["gw_spearman_model"], s["gw_spearman_fpl"])
        ab("MAE vs actual", s["mae_model"], r["mae_model"], s["mae_fpl"])

    d = recent["played_only"]["gw_spearman_model"] - season["played_only"]["gw_spearman_model"]
    print(f"\n  Δ played-only per-GW Spearman (recency − season): {d:+.3f}")
    print(f"  target = close the gap to FPL's {_fmt(season['played_only']['gw_spearman_fpl'])} "
          "(better ranking of players who feature).")


if __name__ == "__main__":
    main()
