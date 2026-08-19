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

from fpledge.eval.fpl_backtest import validate_xp
from fpledge.ingest import vaastav

SEASON = sys.argv[1] if len(sys.argv) > 1 else "2025-26"


def _fmt(x) -> str:
    return f"{x:.3f}" if isinstance(x, float) else str(x)


def main() -> None:
    print(f"downloading vaastav {SEASON} (players + fixtures + teams)...")
    rows = vaastav.fetch_player_gws(SEASON)
    fixtures = vaastav.fetch_fixtures(SEASON)
    teams = vaastav.fetch_teams(SEASON)
    print(f"  {len(rows)} player-GWs, {len(fixtures)} fixtures. Walking forward...")

    print("  A/B: rate-based vs returns-based bonus (minutes: recency; two walk-forwards)...")
    base = validate_xp(rows, fixtures, teams, burn_in=8, minutes_mode="recent", bonus_mode="rate")
    form = validate_xp(rows, fixtures, teams, burn_in=8, minutes_mode="recent", bonus_mode="returns")
    if not base.get("n"):
        print("no scored records.")
        return

    def ab(label: str, a_val, b_val, fpl_val) -> None:
        print(f"    {label:20}  rate-bonus {_fmt(a_val)}   returns-bonus {_fmt(b_val)}   |  FPL {_fmt(fpl_val)}")

    print(f"\n=== xP VALIDATION A/B (bonus) — {SEASON} ({base['n']} player-GWs, {base['gws_scored']} GWs) ===")
    print("  (higher Spearman / lower MAE is better; FPL's own xP is the baseline to beat)")
    for subset, title in (("played_only", "PLAYED only (who to pick)"), ("all_players", "ALL players")):
        a, b = base[subset], form[subset]
        print(f"\n  {title}  ({a['n']} player-GWs):")
        ab("per-GW Spearman", a["gw_spearman_model"], b["gw_spearman_model"], a["gw_spearman_fpl"])
        ab("MAE vs actual", a["mae_model"], b["mae_model"], a["mae_fpl"])

    d = form["played_only"]["gw_spearman_model"] - base["played_only"]["gw_spearman_model"]
    print(f"\n  Δ played-only per-GW Spearman (returns-bonus − rate-bonus): {d:+.3f}")
    print(f"  target = close the gap to FPL's {_fmt(base['played_only']['gw_spearman_fpl'])} "
          "(better ranking of players who feature).")


if __name__ == "__main__":
    main()
