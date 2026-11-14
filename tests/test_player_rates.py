"""The in-season player-rate test: the priors, the wiring through the harness, and the rule."""

from __future__ import annotations

import pytest

from fpledge.eval import player_rates as pr

pytest.importorskip("scipy")


def _prev(code, position, minutes, xg=0.0, xa=0.0, dc=0, bonus=0):
    return {"code": code, "position": position, "minutes": minutes,
            "xg": xg, "xa": xa, "dc": dc, "bonus": bonus}


# --- priors ---------------------------------------------------------------------------------- #
def test_a_regular_last_season_keeps_his_own_per_90():
    got = pr.priors([_prev(7, "FWD", 900, xg=5.0)], {101: (7, "FWD")}, fill="zero")
    assert got[101]["xg"] == pytest.approx(0.5)


def test_production_gives_a_player_without_270_minutes_nothing():
    """The bug under test: six goals this season and a projected zero."""
    got = pr.priors([_prev(7, "FWD", 200, xg=3.0)], {101: (7, "FWD"), 102: (8, "FWD")}, fill="zero")
    assert got[101] == got[102] == dict.fromkeys(pr.STATS, 0.0)


def test_the_blend_prior_falls_back_to_last_seasons_regulars_at_his_position():
    previous = [_prev(1, "FWD", 900, xg=9.0), _prev(2, "FWD", 1800, xg=9.0), _prev(3, "DEF", 900, xg=1.0),
                _prev(4, "FWD", 100, xg=5.0)]                        # under 270: not a regular
    got = pr.priors(previous, {201: (99, "FWD")}, fill="position")
    assert got[201]["xg"] == pytest.approx(18.0 / 30.0)            # 18 xG over 30 nineties


# --- the harness wiring ---------------------------------------------------------------------- #
def _season(gws=4):
    """Club 1 hosts club 2 every week. Striker 11 produces 0.8 xG a game, striker 12 nothing."""
    rows, fixtures = [], []
    for gw in range(1, gws + 1):
        fixtures.append({"gw": gw, "home": "1", "away": "2", "home_goals": 1, "away_goals": 0,
                         "kickoff": f"2026-08-{10 + gw}T15:00:00Z"})
        for el, team, opp, home, xg in ((11, "A", 2, True, 0.8), (12, "A", 2, True, 0.0),
                                        (21, "B", 1, False, 0.3)):
            rows.append({"element": el, "name": str(el), "position": "FWD", "team": team, "gw": gw,
                         "opponent_team": opp, "was_home": home, "minutes": 90, "starts": 1,
                         "xg": xg, "xa": 0.0, "dc": 0, "bonus": 0, "total_points": 2,
                         "fpl_xp": 2.0, "fpl_xp_prev": 2.0})
    return rows, fixtures


def _xp_at(gw, **kwargs):
    from fpledge.eval.fpl_backtest import validate_xp

    rows, fixtures = _season()
    _m, records = validate_xp(rows, fixtures, {"A": 1, "B": 2}, burn_in=1, minutes_mode="recent",
                              fixture_lambdas={(1, 2): (1.6, 0.9)}, return_records=True, **kwargs)
    return {r[1]: r[2] for r in records if r[0] == gw}


_PRIOR = {11: dict.fromkeys(pr.STATS, 0.0), 12: {**dict.fromkeys(pr.STATS, 0.0), "xg": 0.6},
          21: {**dict.fromkeys(pr.STATS, 0.0), "xg": 0.3}}


def test_a_frozen_prior_ignores_this_season_entirely():
    """Production: last season decides all season, so the striker who is producing gets nothing."""
    xp = _xp_at(4, prior_rates=_PRIOR)
    assert xp[12] > xp[11]


def test_a_blend_moves_towards_what_this_season_shows():
    xp = _xp_at(4, prior_rates=_PRIOR, prior_k=1.0)
    assert xp[11] > xp[12]


def test_without_a_prior_the_harness_is_unchanged():
    """The default path predates this test and other results depend on it."""
    assert _xp_at(4) == _xp_at(4, prior_rates=None, prior_k=3.0, rate_half_life=6.0)


# --- comparison and rule --------------------------------------------------------------------- #
def _scores(rhos, season="2024-25", keys=frozenset({1, 2})):
    return {(season, gw): {"rho": r, "abs_err": 10.0, "n": 5, "keys": keys}
            for gw, r in enumerate(rhos, start=2)}


def test_a_better_ranking_is_a_positive_diff():
    got = pr.compare(_scores([0.30, 0.31, 0.29]), _scores([0.33, 0.35, 0.32]))
    assert got["diff"] == pytest.approx(0.0333, abs=1e-3) and got["ci"][0] > 0


def test_variants_must_score_the_same_players():
    with pytest.raises(ValueError, match="different players"):
        pr.compare(_scores([0.3]), _scores([0.3], keys=frozenset({1})))


@pytest.mark.parametrize(("lo", "hi", "mae", "want"), [
    (0.001, 0.02, -0.01, "SHIP"),
    (0.001, 0.02, +0.01, "INCONCLUSIVE"),          # ranks better but misses by more
    (-0.01, 0.02, -0.01, "INCONCLUSIVE"),
    (-0.03, -0.001, 0.0, "DO NOT SHIP"),
])
def test_the_held_out_rule(lo, hi, mae, want):
    assert pr.verdict({"ci": [lo, hi], "mae_diff": mae}) == want


def test_the_rule_picks_k_then_keeps_the_plain_blend_without_clear_evidence_for_form():
    scores = {"production": _scores([0.30] * 6)}
    for k in pr.K_GRID:
        lift = {3: 0.01, 6: 0.03, 10: 0.02, 20: 0.0}[k]
        scores[pr.blend_name(k)] = _scores([0.30 + lift + 0.001 * i for i in range(6)])
        scores[pr.blend_name(k, recent=True)] = _scores([0.30 + lift + 0.001 * (5 - i) for i in range(6)])
    got = pr.choose(scores)
    assert got["k"] == 6
    assert got["candidate"] == pr.blend_name(6)
    assert got["proceed"]


def test_market_lambdas_are_keyed_by_fpl_team_ids():
    match = {"home": "Man United", "away": "Fulham", "close_h": 1.65, "close_d": 4.2, "close_a": 5.3,
             "close_over25": 1.8, "close_under25": 2.05}
    got = pr.market_fixture_lambdas([match], {"Man Utd": 14, "Fulham": 10})
    lam_h, lam_a = got[(14, 10)]
    assert lam_h > lam_a > 0
