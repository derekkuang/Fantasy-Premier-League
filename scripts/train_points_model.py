#!/usr/bin/env python3
"""Train + validate the LightGBM points model; A/B vs the structured xP and FPL's xP.

Walk-forward on vaastav data, scored on the same harness metric so all three are comparable.

Usage: python scripts/train_points_model.py [season]   (default 2025-26)
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import scipy.stats as st

from fpledge.eval.fpl_backtest import _score
from fpledge.ingest import vaastav
from fpledge.models.points_ml import (
    extract_features,
    structured_records,
    walk_forward_lgbm,
)

SEASON = sys.argv[1] if len(sys.argv) > 1 else "2025-26"


def _fmt(x) -> str:
    return f"{x:.3f}" if isinstance(x, float) else str(x)


def main() -> None:
    print(f"downloading vaastav {SEASON}...")
    rows = vaastav.fetch_player_gws(SEASON)
    fixtures = vaastav.fetch_fixtures(SEASON)
    teams = vaastav.fetch_teams(SEASON)

    print(f"  extracting point-in-time features from {len(rows)} player-GWs...")
    feats = extract_features(rows, fixtures, teams, burn_in=8)
    print(f"  {len(feats)} feature rows; walk-forward LightGBM (regression + rank, retrain each GW)...")
    reg = walk_forward_lgbm(feats, objective="regression")
    rnk = walk_forward_lgbm(feats, objective="rank")
    tested = {r[0] for r in reg} & {r[0] for r in rnk}
    m_struct = _score(structured_records(feats, only_gws=tested), st)
    m_reg = _score([r for r in reg if r[0] in tested], st)
    m_rnk = _score([r for r in rnk if r[0] in tested], st)

    def line(label: str, s, lr, lk, f) -> None:
        print(f"    {label:16} struct {_fmt(s)}  LGBM-reg {_fmt(lr)}  LGBM-rank {_fmt(lk)}  | FPL {_fmt(f)}")

    print(f"\n=== POINTS MODEL A/B — {SEASON} ({m_rnk['n']} player-GWs, {m_rnk['gws_scored']} GWs) ===")
    print("  (higher Spearman / lower MAE is better; FPL's own xP is the ceiling)")
    for subset, title in (("played_only", "PLAYED only (who to pick)"), ("all_players", "ALL players")):
        s, lr, lk = m_struct[subset], m_reg[subset], m_rnk[subset]
        print(f"\n  {title} ({lk['n']} player-GWs):")
        line("per-GW Spearman", s["gw_spearman_model"], lr["gw_spearman_model"],
             lk["gw_spearman_model"], lk["gw_spearman_fpl"])
        line("MAE vs actual", s["mae_model"], lr["mae_model"], lk["mae_model"], lk["mae_fpl"])

    ranked = sorted(
        [("structured", m_struct), ("LGBM-reg", m_reg), ("LGBM-rank", m_rnk)],
        key=lambda kv: kv[1]["played_only"]["gw_spearman_model"] or 0.0, reverse=True,
    )
    print("\n  played-only per-GW Spearman, best-first: "
          + ", ".join(f"{name} {_fmt(m['played_only']['gw_spearman_model'])}" for name, m in ranked))
    print(f"  FPL ceiling {_fmt(m_rnk['played_only']['gw_spearman_fpl'])}")


if __name__ == "__main__":
    main()
