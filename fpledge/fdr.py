"""True fixture difficulty (FDR) from the engine's expected goals, over the next N GWs.

FPL's own FDR is a crude static 1-5. This derives difficulty from the Dixon-Coles engine's
per-fixture expected goals, split the way managers actually use it:
  * ATTACK difficulty  — from a team's expected goals FOR (high => easy for its attackers)
  * DEFENCE difficulty — from its expected goals AGAINST (low => likely clean sheet)
Both mapped to a 1 (easiest) - 5 (hardest) scale.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

# (upper-bound, rating) thresholds on expected goals — tuned to the engine's ~0.7-3.0 range.
_ATTACK_BANDS = [(1.15, 5), (1.35, 4), (1.6, 3), (1.9, 2)]   # low goals-for = hard to attack
_DEFENCE_BANDS = [(0.9, 1), (1.1, 2), (1.35, 3), (1.6, 4)]   # low goals-against = easy CS


def attack_fdr(lam_for: float) -> int:
    """1 (easy to score) .. 5 (hard) from a team's expected goals FOR."""
    for upper, rating in _ATTACK_BANDS:
        if lam_for < upper:
            return rating
    return 1


def defence_fdr(lam_against: float) -> int:
    """1 (likely clean sheet) .. 5 (leaky) from a team's expected goals AGAINST."""
    for upper, rating in _DEFENCE_BANDS:
        if lam_against < upper:
            return rating
    return 5


def _label(team_id, fpl_teams, tmap):
    return tmap.get(fpl_teams.get(team_id)) or f"__unknown__:{team_id}"


def fixture_ticker(
    engine,
    fixtures: Sequence[dict],
    fpl_teams: dict,
    tmap: dict,
    start_gw: int,
    horizon: int = 5,
    market_lambdas: dict | None = None,
) -> dict:
    """Per team, the upcoming `horizon` fixtures with expected goals + FDR ratings.

    fixtures: dicts with gw, home_id, away_id. Returns {team_id: [fixture-dicts sorted by gw]}.
    Each row is tagged `source`: "market" when a de-vigged betting line supplied the lambdas
    (near gameweeks), else "model" (the engine). The UI reads lam_for + lam_against for the
    high/low-scoring and favourite cues.
    """
    ticker: dict = defaultdict(list)
    for fx in fixtures:
        if not (start_gw <= fx["gw"] < start_gw + horizon):
            continue
        h, a = fx["home_id"], fx["away_id"]
        mkt = market_lambdas.get((h, a)) if market_lambdas else None
        if mkt is not None:
            lam_home, lam_away, source = mkt[0], mkt[1], "market"
        else:
            pred = engine.predict(_label(h, fpl_teams, tmap), _label(a, fpl_teams, tmap))
            lam_home, lam_away, source = pred.lam_home, pred.lam_away, "model"
        ticker[h].append({
            "gw": fx["gw"], "opp_id": a, "opp": fpl_teams.get(a), "home": True,
            "lam_for": lam_home, "lam_against": lam_away,
            "attack_fdr": attack_fdr(lam_home), "defence_fdr": defence_fdr(lam_away),
            "source": source,
        })
        ticker[a].append({
            "gw": fx["gw"], "opp_id": h, "opp": fpl_teams.get(h), "home": False,
            "lam_for": lam_away, "lam_against": lam_home,
            "attack_fdr": attack_fdr(lam_away), "defence_fdr": defence_fdr(lam_home),
            "source": source,
        })
    for rows in ticker.values():
        rows.sort(key=lambda x: x["gw"])
    return dict(ticker)
