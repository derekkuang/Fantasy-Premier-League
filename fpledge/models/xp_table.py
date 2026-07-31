"""Assemble per-player expected-points (xP) records for a gameweek.

The single code path shared by the xP table (`scripts/build_xp.py`) and the squad
optimiser (`scripts/build_squad.py`): given loaded players + fixtures + a fitted engine
+ a FPL->Football-Data team map + prices, produce one record per player whose fixture is
predictable, with xP and the rank-relative fields.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence

from . import rank
from .minutes import MinutesModel
from .shares import match_shares, team_minutes
from .xpoints import (
    PlayerContext,
    dc_point_probability,
    expected_bonus,
    expected_conceded_penalty,
    expected_points_breakdown,
)

LOW_COVERAGE = 9000       # current-squad last-season minutes below this -> shares unreliable
MIN_RATE_MINUTES = 270    # need this many last-season minutes to trust a per-90 rate


def compute_xp_records(
    players: Sequence[dict],
    fpl_teams: dict,
    fixtures: Sequence[tuple],
    engine,  # noqa: ANN001 — fitted DixonColesModel
    tmap: dict,
    prices: dict,
    availability: dict | None = None,
    low_coverage: int = LOW_COVERAGE,
    min_rate_minutes: int = MIN_RATE_MINUTES,
    market_lambdas: dict | None = None,
):
    """Return (records, skipped_fixtures, coverage).

    records: list of dicts with code, element_id, web_name, position, team_id, team_name,
    price, x_minutes, xp, ownership, eo, diff_value, captain_score, low_cov.
    A fixture is skipped when either team is unknown to the engine (e.g. promoted).
    """
    minutes_model = MinutesModel()

    def _pred(p):  # noqa: ANN001 — season proxy, discounted by live availability if provided
        mp = minutes_model.from_season(p["minutes"], p["starts"])
        if availability:
            chance, status = availability.get(p["code"], (None, None))
            mp = minutes_model.apply_availability(mp, chance, status)
        return mp

    minutes_pred = {p["code"]: _pred(p) for p in players}
    x_minutes = {code: mp.x_minutes for code, mp in minutes_pred.items()}
    shares = match_shares(players, x_minutes)
    coverage = team_minutes(players)
    by_team: dict = defaultdict(list)
    for p in players:
        by_team[p["team_id"]].append(p)

    records, fallback = [], []
    for home_id, away_id in fixtures:
        home_name, away_name = fpl_teams.get(home_id), fpl_teams.get(away_id)
        # map to the engine's team names; an unmapped/unknown team gets a sentinel label so
        # the engine falls back to its promoted-side prior (coverage fix #4/#6) rather than skip.
        home_fd = tmap.get(home_name) or f"__unknown__:{home_id}"
        away_fd = tmap.get(away_name) or f"__unknown__:{away_id}"
        if not (engine.knows(home_fd) and engine.knows(away_fd)):
            fallback.append((home_name, away_name))
        mkt = market_lambdas.get((home_id, away_id)) if market_lambdas else None
        if mkt is not None:
            # market-implied lambdas; clean sheet ~ P(opponent scores 0) under Poisson.
            lh, la = mkt
            sides = [
                (home_id, lh, math.exp(-la), la),
                (away_id, la, math.exp(-lh), lh),
            ]
        else:
            pred = engine.predict(home_fd, away_fd)
            sides = [
                (home_id, pred.lam_home, pred.clean_sheet_home, pred.lam_away),
                (away_id, pred.lam_away, pred.clean_sheet_away, pred.lam_home),
            ]
        for team_id, team_lambda, p_cs, opp_lambda in sides:
            low_cov = coverage.get(team_id, 0) < low_coverage
            for p in by_team.get(team_id, []):
                mp = minutes_pred[p["code"]]
                sh = shares.get(p["code"], {"goal_share": 0.0, "assist_share": 0.0})
                if low_cov:
                    # Promoted / low-data team: teammates have no history, so normalising
                    # shares to sum to 1 hands the one player WITH data ~100% of the team's
                    # goals, inflating a tiny per-90 rate up to the full team lambda (the
                    # "Diop" artifact). We can't trust attacking attribution here — drop it.
                    # Appearance / clean-sheet / defensive-contribution stay (fixture-based).
                    sh = {"goal_share": 0.0, "assist_share": 0.0}
                per90 = p["minutes"] / 90.0
                trust = p["minutes"] >= min_rate_minutes
                dc_per90 = (p["dc"] / per90) if trust else 0.0
                bonus_per90 = (p["bonus"] / per90) if trust else 0.0
                ctx = PlayerContext(
                    position=p["position"],
                    p_play=mp.p_play,
                    p_60=mp.p_60,
                    team_lambda=team_lambda,
                    goal_share=sh["goal_share"],
                    assist_share=sh["assist_share"],
                    p_clean_sheet=p_cs,
                    x_saves=(opp_lambda * 3.0 * (mp.x_minutes / 90.0) if p["position"] == "GK" else 0.0),
                    p_dc_point=dc_point_probability(dc_per90, mp.x_minutes, p["position"]),
                    x_bonus=expected_bonus(bonus_per90, mp.x_minutes),
                    opp_lambda=opp_lambda,
                    x_conceded_penalty=(
                        expected_conceded_penalty(opp_lambda, mp.x_minutes)
                        if p["position"] in ("GK", "DEF") else 0.0
                    ),
                )
                bd = expected_points_breakdown(ctx)
                xp = bd["total"]
                eo = rank.effective_ownership(p["ownership"])
                records.append(
                    {
                        "code": p["code"],
                        "element_id": p["element_id"],
                        "web_name": p["web_name"],
                        "position": p["position"],
                        "team_id": team_id,
                        "team_name": fpl_teams.get(team_id),
                        "price": prices.get(p["code"]),
                        "x_minutes": mp.x_minutes,
                        "xp": xp,
                        "ownership": p["ownership"],
                        "eo": eo,
                        "diff_value": rank.differential_value(xp, eo),
                        "captain_score": rank.captain_rank_score(xp, eo),
                        "low_cov": low_cov,
                        "breakdown": bd,
                    }
                )
    return records, fallback, coverage


def compute_multi_gw_xp(
    players: Sequence[dict],
    fpl_teams: dict,
    fixtures_by_gw: dict,
    engine,  # noqa: ANN001 — fitted DixonColesModel
    tmap: dict,
    prices: dict,
    ticker: dict,
    gws: Sequence[int],
    availability: dict | None = None,
    market_lambdas: dict | None = None,
):
    """Per-player xP for each upcoming gameweek, joined to the fixture + true FDR.

    Reuses `compute_xp_records` per GW (same engine / minutes / shares, only the opponent
    changes) and joins each player to their team's fixture-difficulty from `ticker`.
    Returns {element_id: [{gw, opp, home, xp, fdr}, ...]} ordered by gw. Double gameweeks
    sum a team's xP; blank gameweeks are simply absent from a player's list.
    """
    tick = {(tid, f["gw"]): f for tid, fxs in ticker.items() for f in fxs}
    per_player: dict = defaultdict(list)
    for g in gws:
        recs, _, _ = compute_xp_records(
            players, fpl_teams, fixtures_by_gw.get(g, []), engine, tmap, prices,
            availability=availability, market_lambdas=market_lambdas,
        )
        xp_by_el: dict = defaultdict(float)
        meta: dict = {}
        for r in recs:
            xp_by_el[r["element_id"]] += r["xp"]  # sum over a double gameweek
            meta[r["element_id"]] = (r["team_id"], r["position"])
        for el, xp in xp_by_el.items():
            team_id, pos = meta[el]
            fx = tick.get((team_id, g))
            if fx is None:
                continue
            fdr = fx["defence_fdr"] if pos in ("GK", "DEF") else fx["attack_fdr"]
            per_player[el].append(
                {"gw": g, "opp": fx["opp"], "home": fx["home"], "xp": round(xp, 2), "fdr": fdr}
            )
    return dict(per_player)
