"""The card term, the assist factor and the E3/E4 decision helpers (docs/MODEL_FIXES.md)."""

import pytest

from fpledge.eval import cards_assists as ca
from fpledge.models.xpoints import PlayerContext, expected_card_points, expected_points_breakdown


def test_card_points():
    # 0.2 yellows and 0.01 reds per 90, a full game: -(0.2 + 0.03)
    assert expected_card_points(0.2, 0.01, 90) == pytest.approx(-0.23)
    assert expected_card_points(0.2, 0.01, 45) == pytest.approx(-0.115)
    assert expected_card_points(0.2, 0.0, 0) == 0.0


def test_card_term_is_off_unless_given():
    ctx = dict(position="MID", p_play=1.0, p_60=1.0, team_lambda=1.4, goal_share=0.1,
               assist_share=0.1, p_clean_sheet=0.3)
    base = expected_points_breakdown(PlayerContext(**ctx))
    assert base["card_points"] == 0.0
    carded = expected_points_breakdown(PlayerContext(**ctx, x_card_points=-0.2))
    assert carded["total"] == pytest.approx(base["total"] - 0.2)


def test_card_prior_uses_regulars_only():
    prev = [{"position": "DEF", "minutes": 900, "yellow_cards": 2, "red_cards": 1},
            {"position": "DEF", "minutes": 900, "yellow_cards": 0, "red_cards": 0},
            {"position": "DEF", "minutes": 100, "yellow_cards": 5, "red_cards": 0},
            {"position": None, "minutes": 900, "yellow_cards": 9, "red_cards": 0}]
    assert ca.card_prior(prev) == {"DEF": (pytest.approx(0.1), pytest.approx(0.05))}


def test_assist_factors():
    pairs = [("FWD", 0.05, 0), ("FWD", 0.05, 1), ("FWD", 0.9, 0), ("MID", 0.5, 0), ("MID", 0.5, 1),
             ("GK", 0.01, 0)]
    assert ca.assist_factors(pairs) == {"FWD": 1.0, "MID": 1.0}


def test_mse_and_compare():
    recs_a = [(2, 1, 2.0, 0, 6, "MID", 90), (2, 2, 2.0, 0, 1, "DEF", 30), (2, 3, 1.0, 0, 0, "DEF", 0)]
    recs_b = [(2, 1, 3.0, 0, 6, "MID", 90), (2, 2, 2.0, 0, 1, "DEF", 30), (2, 3, 1.0, 0, 0, "DEF", 0)]
    a, b = ca.mse_by_gw(recs_a, "s"), ca.mse_by_gw(recs_b, "s")
    assert a[("s", 2)]["n"] == 2                    # the player who did not play is not scored
    r = ca.compare_mse(a, b)
    assert r["mse_a"] == pytest.approx((16 + 1) / 2) and r["mse_b"] == pytest.approx((9 + 1) / 2)
    assert r["bias_a"]["MID"] == pytest.approx(4.0) and r["bias_b"]["MID"] == pytest.approx(3.0)


def test_verdict():
    assert ca.verdict({"ci": [-0.02, -0.01]}, {"ci": [-0.001, 0.003]}) == "SHIP"
    assert ca.verdict({"ci": [-0.02, 0.01]}, {"ci": [-0.001, 0.003]}) == "INCONCLUSIVE"
    assert ca.verdict({"ci": [0.01, 0.02]}, {"ci": [0.0, 0.003]}) == "DO NOT SHIP"


def test_expected_to_play_rows_keep_the_zeros():
    # an expected starter who did not play stays in, scored against his 0
    recs = [(2, 1, 4.0, 0, 6, "MID", 90), (2, 2, 3.0, 0, 0, "MID", 0), (2, 3, 0.5, 0, 2, "DEF", 20)]
    played = ca.mse_by_gw(recs, "s")[("s", 2)]
    expected = ca.mse_by_gw(recs, "s", include={(2, 1), (2, 2)})[("s", 2)]
    assert played["n"] == 2 and played["keys"] == frozenset({1, 3})
    assert expected["n"] == 2 and expected["keys"] == frozenset({1, 2})
    assert expected["sq"] == pytest.approx(4 + 9)
