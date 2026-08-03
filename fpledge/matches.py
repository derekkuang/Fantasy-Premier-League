"""Per-match previews: the full scoreline distribution, serialised for serving.

The engine already builds a `MatchProbabilities` for every fixture — `compute_xp_records`
constructs one, reads `clean_sheet_home` off it, and discards the rest; `fixture_ticker` keeps
only the two lambdas. So the richest object in the system (an 11x11 scoreline matrix and every
market derived from it) is computed on each precompute and then thrown away.

This module serialises it. Nothing here is a new model — it is the same `derive()` output the
xP path already depends on, reshaped for the API.

On the matrix: the full 121 cells per fixture would bloat the payload for no gain, so only the
most likely scorelines are kept, plus `scorelines_p` stating how much probability mass that
covers. A UI can then say "these N results account for 62% of outcomes" honestly, rather than
implying the list is exhaustive.
"""

from __future__ import annotations

from collections.abc import Sequence

from .fdr import attack_fdr, defence_fdr
from .models.match_engine import derive

TOP_SCORELINES = 8


def match_id(gw: int, home_id: int, away_id: int) -> str:
    """Stable identifier for a fixture within a season (the FPL fixture id isn't carried
    through the serving payload, and a gw+pairing is unique)."""
    return f"{gw}-{home_id}-{away_id}"


def _top_scorelines(matrix: Sequence[Sequence[float]], top: int = TOP_SCORELINES) -> tuple[list[dict], float]:
    cells = [
        {"home": i, "away": j, "p": p}
        for i, row in enumerate(matrix)
        for j, p in enumerate(row)
    ]
    cells.sort(key=lambda c: c["p"], reverse=True)
    kept = cells[:top]
    return (
        [{"home": c["home"], "away": c["away"], "p": round(c["p"], 4)} for c in kept],
        round(sum(c["p"] for c in kept), 4),
    )


def _label(team_id, fpl_teams, tmap):
    return tmap.get(fpl_teams.get(team_id)) or f"__unknown__:{team_id}"


def match_previews(
    engine,
    fixtures: Sequence[dict],
    fpl_teams: dict,
    tmap: dict,
    start_gw: int,
    horizon: int = 8,
    market_lambdas: dict | None = None,
) -> list[dict]:
    """One preview per fixture in [start_gw, start_gw+horizon), ordered by gameweek.

    `fixtures` are dicts with gw/home_id/away_id — the same shape `fixture_ticker` takes.

    When a de-vigged betting line is available the market's lambdas replace the engine's and
    the row is tagged `source: "market"`; the distribution is then derived from those lambdas
    the same way, so a market-sourced preview is the market's own implied scoreline spread.
    """
    out: list[dict] = []
    for fx in fixtures:
        if not (start_gw <= fx["gw"] < start_gw + horizon):
            continue
        h, a = fx["home_id"], fx["away_id"]
        mkt = market_lambdas.get((h, a)) if market_lambdas else None
        if mkt is not None:
            probs, source = derive(mkt[0], mkt[1]), "market"
        else:
            probs, source = engine.predict(_label(h, fpl_teams, tmap), _label(a, fpl_teams, tmap)), "model"

        scorelines, covered = _top_scorelines(probs.matrix)
        out.append({
            "match_id": match_id(fx["gw"], h, a),
            "gw": fx["gw"],
            "home_id": h, "home": fpl_teams.get(h),
            "away_id": a, "away": fpl_teams.get(a),
            "source": source,
            "lam_home": round(probs.lam_home, 3),
            "lam_away": round(probs.lam_away, 3),
            "result": {
                "home_win": round(probs.home_win, 4),
                "draw": round(probs.draw, 4),
                "away_win": round(probs.away_win, 4),
            },
            "btts": round(probs.btts, 4),
            "over_2_5": round(probs.over_2_5, 4),
            "under_2_5": round(1.0 - probs.over_2_5, 4),
            # P(the OTHER side fails to score) — the number the FPL clean-sheet term uses
            "clean_sheet": {
                "home": round(probs.clean_sheet_home, 4),
                "away": round(probs.clean_sheet_away, 4),
            },
            "most_likely_score": list(probs.most_likely_score),
            "scorelines": scorelines,
            "scorelines_p": covered,   # mass covered by `scorelines`; the rest is the tail
            "fdr": {
                "home": {"attack": attack_fdr(probs.lam_home), "defence": defence_fdr(probs.lam_away)},
                "away": {"attack": attack_fdr(probs.lam_away), "defence": defence_fdr(probs.lam_home)},
            },
        })
    out.sort(key=lambda m: (m["gw"], m["home"] or ""))
    return out
