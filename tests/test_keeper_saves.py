"""Keeper save points with FPL's per-match rounding, and the §41 decision helpers."""

import math

import pytest

from fpledge.eval import keeper_saves as ks
from fpledge.models.xpoints import PlayerContext, expected_points_breakdown, expected_save_points


def _poisson_floor_mean(m, per=3, terms=12):
    sf = lambda k: 1 - sum(math.exp(-m) * m**i / math.factorial(i) for i in range(k))
    return sum(sf(per * k) for k in range(1, terms))


def test_save_points_round_down_per_match():
    # three expected saves: E[floor(S/3)] for S ~ Poisson(3) is about 0.665, not 1.0
    assert expected_save_points(3.0, 90) == pytest.approx(_poisson_floor_mean(3.0), abs=1e-9)
    assert expected_save_points(3.0, 90) == pytest.approx(0.6646, abs=1e-3)
    assert expected_save_points(3.0, 90) < 3.0 / 3


def test_save_points_scale_with_time_on_the_pitch():
    # half the minutes: the same match rate, half the weight
    assert expected_save_points(1.5, 45) == pytest.approx(0.5 * expected_save_points(3.0, 90))
    assert expected_save_points(0.0, 90) == 0.0
    assert expected_save_points(2.0, 0) == 0.0


def _ctx(**kw):
    base = dict(position="GK", p_play=1.0, p_60=1.0, team_lambda=1.2, goal_share=0.0,
                assist_share=0.0, p_clean_sheet=0.3, x_saves=3.0)
    return PlayerContext(**{**base, **kw})


def test_breakdown_uses_rounded_points_when_given():
    assert expected_points_breakdown(_ctx())["save_points"] == pytest.approx(1.0)   # legacy linear
    bd = expected_points_breakdown(_ctx(x_save_points=0.66))
    assert bd["save_points"] == pytest.approx(0.66)
    assert expected_points_breakdown(_ctx(position="DEF", x_save_points=0.66))["save_points"] == 0.0


def test_fit_saves_per_goal_counts_only_played_fixtures():
    pairs = [(4, 90, 2.0), (1, 45, 1.0), (9, 0, 3.0)]
    assert ks.fit_saves_per_goal(pairs) == round(5 / (2.0 + 0.5), 2)
    with pytest.raises(ValueError):
        ks.fit_saves_per_goal([(3, 0, 1.0)])


def test_verdict():
    good = {"ci": [-0.2, -0.1]}
    assert ks.verdict(good, {"ci": [-0.001, 0.004]}) == "SHIP"
    assert ks.verdict(good, {"ci": [-0.003, 0.004]}) == "INCONCLUSIVE"
    assert ks.verdict({"ci": [0.01, 0.2]}, {"ci": [0.0, 0.01]}) == "DO NOT SHIP"
    assert ks.verdict(good, {"ci": [-0.01, -0.001]}) == "DO NOT SHIP"
