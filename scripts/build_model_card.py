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

Usage: python scripts/build_model_card.py [season]      (default 2025-26)
"""

from __future__ import annotations

import json
import pathlib
import sys
from datetime import UTC, datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpledge import config
from fpledge.api import MODEL_VER
from fpledge.eval.fpl_backtest import validate_xp
from fpledge.ingest import vaastav

SEASON = sys.argv[1] if len(sys.argv) > 1 else "2025-26"
OUT = config.DATA_DIR / "eval" / "model_card.json"

# --- recorded experiments ------------------------------------------------------------- #
# Every A/B that has been run against the validation harness, kept whether it worked or not.
# The nulls are the point: a list containing only wins is a marketing page, not a model card.
EXPERIMENTS = [
    {
        "name": "Recency-weighted minutes",
        "question": "Does weighting recent appearances beat a season-long average?",
        "delta": "+0.064 all-players per-GW Spearman (0.669 → 0.733)",
        "verdict": "kept",
        "measured": "2026-07-26",
    },
    {
        "name": "Recency-weighted xG/xA",
        "question": "Same idea, applied to attacking rates instead of minutes.",
        "delta": "+0.002 played-only per-GW Spearman",
        "verdict": "null — attacking form is not the gap",
        "measured": "2026-07-26",
    },
    {
        "name": "Returns-based expected bonus",
        "question": "Estimate bonus from goal/assist involvement rather than a flat rate.",
        "delta": "+0.002 played-only per-GW Spearman",
        "verdict": "null",
        "measured": "2026-07-27",
    },
    {
        "name": "LightGBM points model",
        "question": "Can a gradient booster learn single-gameweek points better than the structured model?",
        "delta": "structured 0.320 vs LGBM-regression 0.277 vs LGBM-rank 0.244",
        "verdict": "rejected — the learned model is WORSE; single-GW points are too noisy "
                   "and the public feature set too thin, so it fits the noise",
        "measured": "2026-07-27",
    },
    {
        "name": "Goals-conceded penalty for GK/DEF",
        "question": "Does modelling the −1 per 2 conceded help?",
        "delta": "+0.009 played-only per-GW Spearman",
        "verdict": "kept",
        "measured": "2026-07-30",
    },
    {
        "name": "Market-implied lambdas",
        "question": "Blend de-vigged betting odds into the match model's expected goals.",
        "delta": "+0.0085 played-only per-GW Spearman",
        "verdict": "kept — dormant in preseason, activates when books post lines",
        "measured": "2026-07-31",
    },
]

# --- the honest limits ---------------------------------------------------------------- #
NOT_MODELLED: dict[str, str] = {
    "Price changes": (
        "There is no price-change forecast here. The site shows what prices HAVE done, "
        "never what they will do."
    ),
    "True effective ownership": (
        "Ownership is `selected_by_percent` — how many managers own a player, not how many "
        "captain them. Every differential and captain figure inherits that approximation."
    ),
    "Chip timing": (
        "Wildcard, Bench Boost, Triple Captain and Free Hit are not simulated."
    ),
    "Multi-gameweek planning": (
        "The optimiser maximises a single gameweek. It will not tell you to take a worse "
        "week now for a better run later."
    ),
    "Bench order and auto-subs": (
        "The bench is ranked but auto-substitution is not simulated, so a projection "
        "assumes your XI plays."
    ),
    "Promoted and low-data clubs": (
        "Clubs without enough history get a prior instead of estimated attacking shares, "
        "and are excluded from rankings rather than shown with a made-up number."
    ),
    "Team news beyond the official flag": (
        "Availability comes from FPL's own status field. A press-conference hint that "
        "hasn't reached the API has not reached this model either."
    ),
    "Where a team attacks": (
        "Shot-location and defensive-duel data would need Opta-grade inputs. The Understat "
        "approximation is built but its fetch adapters are currently broken upstream."
    ),
}

METHOD = {
    "engine": "Dixon-Coles, fitted from scratch by maximum likelihood with time decay — not a "
              "library import. It emits a full scoreline probability matrix per fixture; every "
              "downstream number (clean sheet, BTTS, FDR) is a sum over that matrix.",
    "xp": "Expected points is a structured expected-value calculation, not a learned regressor: "
          "each scoring category is modelled separately and the terms sum to the total. That is "
          "why every projection on the site can be opened up and read term by term.",
    "validation": "Walk-forward on a completed season. For gameweek N the model sees only "
                  "gameweeks before N — rolling rates and a match engine refit on earlier "
                  "fixtures — then is scored against what actually happened. A leakage test "
                  "guards the boundary.",
    "metric": "Per-gameweek Spearman rank correlation against realised points, averaged over "
              "gameweeks. Rank correlation rather than error, because picking a squad is a "
              "ranking problem: what matters is the ORDER, not the absolute points.",
    "baseline": "FPL's own published expected points for the gameweek, taken from the `xP` "
                "column of the community dataset and scored on exactly the same players in "
                "exactly the same gameweeks as ours. IMPORTANT: that column is not populated "
                "for every gameweek — a gameweek only counts here when BOTH projections exist "
                "for it, and `baseline_gws` says how many did. A thin baseline is reported as "
                "thin rather than averaged around.",
}


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

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(card, indent=2))

    p = card["measured"]["played_only"]
    a = card["measured"]["all_players"]
    print(f"\n=== MODEL CARD — {SEASON} ({res['n']} player-GWs, {res['gws_scored']} GWs) ===")
    print(f"  played-only per-GW Spearman   model {p['spearman_model']}  vs FPL {p['spearman_fpl']}")
    print(f"  all-players per-GW Spearman   model {a['spearman_model']}  vs FPL {a['spearman_fpl']}")
    print(f"  played-only MAE               model {p['mae_model']}  vs FPL {p['mae_fpl']}")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
