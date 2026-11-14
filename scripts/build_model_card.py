#!/usr/bin/env python3
"""Generate the model card the /model page reads.

The site claims its projections are "about on par with FPL's own" and promises to show where
the model loses. That claim has to come from somewhere reproducible, so it comes from here:
a walk-forward validation on a completed season, written to a JSON artifact that the API
serves and the page renders. Nothing about the honesty page is typed into a template by hand.

Two kinds of content, kept separate on purpose:

  MEASURED  — recomputed on every run of this script, from `eval.fpl_backtest.validate_xp`.
              This is the headline claim and it is only ever as old as the artifact.
  RECORDED  — results of experiments already run, with the date they were run. A LightGBM
              training run or an odds backtest is too slow and too dependency-heavy to
              redo on every card build, but an experiment that happened is still evidence.
              It is labelled as recorded rather than dressed up as fresh.

Usage: python scripts/build_model_card.py [season]      (default 2024-25)

Writes through the serving store, so it lands wherever `FPLEDGE_SERVING_URI` points. To publish
to production, run it with that set to the production bucket — the precompute does not rebuild
the card, because a walk-forward over a completed season does not change week to week.
"""

from __future__ import annotations

import pathlib
import sys
from datetime import UTC, datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpledge.api import MODEL_VER, store
from fpledge.eval.fpl_backtest import validate_xp
from fpledge.ingest import vaastav
from fpledge.model_notes import EXPERIMENTS, METHOD, NOT_MODELLED

# 2024-25, not the latest season, because the comparison is only as good as FPL's side of it.
# The clean pre-deadline baseline covers 29 of 30 scored gameweeks there and 4 in 2025-26
# (1,211 player-GWs), which would set our 30-gameweek number against FPL's 4-gameweek one.
# Rebuild on a newer season once the snapshots give it a full baseline.
SEASON = sys.argv[1] if len(sys.argv) > 1 else "2024-25"
# A serving artifact, read by GET /model. It was a file under data/eval/, which the API read
# straight off local disk — present on the machine that built it and nowhere else.
ARTIFACT = "model_card.json"

# What we tried, what the model doesn't know and how it works live in fpledge/model_notes.py,
# so the page's text can be corrected without rebuilding the measured card.


def _r(x, n=3):
    return None if x is None else round(x, n)


def main() -> None:
    print(f"downloading vaastav {SEASON}...")
    rows = vaastav.fetch_player_gws(SEASON)
    fixtures = vaastav.fetch_fixtures(SEASON)
    teams = vaastav.fetch_teams(SEASON)
    print(f"  {len(rows)} player-GWs. Walking forward (this is the slow part)...")

    res = validate_xp(rows, fixtures, teams, burn_in=8, minutes_mode="recent", bonus_mode="rate")
    if not res.get("n"):
        sys.exit("no records scored — the season data may be empty")

    def subset(key: str) -> dict:
        s = res[key]
        return {
            "n": s["n"],
            "spearman_model": _r(s["gw_spearman_model"]),
            "spearman_fpl": _r(s["gw_spearman_fpl"]),
            # MAE on the same records the ranking comparison used, so both metrics describe
            # the same gameweeks. `mae_model_all` is our error everywhere we scored.
            "mae_model": _r(s["mae_model_common"]),
            "mae_model_all": _r(s["mae_model"]),
            "mae_fpl": _r(s["mae_fpl"]),
            "gws_model_mae_beats_fpl": s["gws_model_mae_beats_fpl"],
            "baseline_gws": s["baseline_gws"],
            "baseline_n": s["baseline_n"],
        }

    card = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "season": SEASON,
        "model_ver": MODEL_VER,
        "measured": {
            "n_player_gws": res["n"],
            "gws_scored": res["gws_scored"],
            "played_only": subset("played_only"),
            "all_players": subset("all_players"),
            "mae_by_position_played": {k: _r(v, 2) for k, v in res["mae_by_position_played"].items()},
        },
        "method": METHOD,
        "experiments": EXPERIMENTS,
        "not_modelled": [{"topic": t, "detail": d} for t, d in NOT_MODELLED.items()],
    }

    locator = store.write_artifact(ARTIFACT, card)

    p = card["measured"]["played_only"]
    a = card["measured"]["all_players"]
    print(f"\n=== MODEL CARD — {SEASON} ({res['n']} player-GWs, {res['gws_scored']} GWs) ===")
    print(f"  played-only per-GW Spearman   model {p['spearman_model']}  vs FPL {p['spearman_fpl']}")
    print(f"  all-players per-GW Spearman   model {a['spearman_model']}  vs FPL {a['spearman_fpl']}")
    print(f"  played-only MAE               model {p['mae_model']}  vs FPL {p['mae_fpl']}")
    print(f"\nwrote {locator}")


if __name__ == "__main__":
    main()
