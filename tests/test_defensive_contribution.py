"""Defensive contribution taken case by case (HANDOFF §42) and the test's decision helpers."""

import math

import pytest

from fpledge.eval import defensive_contribution as dc
from fpledge.models.xpoints import (
    _nbinom_sf,
    _poisson_sf,
    dc_point_probability,
    dc_point_probability_by_case,
)


def test_negative_binomial_tail():
    # a huge size is Poisson; a small one has the fatter tail
    assert _nbinom_sf(10, 8.0, 1e7) == pytest.approx(_poisson_sf(10, 8.0), abs=1e-5)
    assert _nbinom_sf(10, 8.0, 5) > _poisson_sf(10, 8.0)
    # against the pmf summed by hand: size 2, mean 2 -> p = 0.5, P(X=k) = (k+1) / 2^(k+2)
    assert _nbinom_sf(3, 2.0, 2) == pytest.approx(1 - sum((k + 1) / 2 ** (k + 2) for k in range(3)))
    assert _nbinom_sf(0, 0.0, 5) == 1.0 and _nbinom_sf(3, 0.0, 5) == 0.0


def test_a_nailed_starter_is_unchanged():
    assert dc_point_probability_by_case(9, 1.0, 1.0, 88, "DEF") == pytest.approx(
        dc_point_probability(9, 88, "DEF"))


def test_a_rotation_player_is_weighted_not_crushed():
    # 60% to play a full game (86 min), 10% to come on: the tail is taken at full-game minutes
    x_min = 0.6 * 86 + 0.1 * 22
    by_case = dc_point_probability_by_case(9, 0.7, 0.6, x_min, "DEF")
    assert by_case == pytest.approx(0.6 * _poisson_sf(10, 9 * 86 / 90) + 0.1 * _poisson_sf(10, 9 * 22 / 90))
    assert by_case > 4 * dc_point_probability(9, x_min, "DEF")


def test_cases_and_positions():
    assert dc_point_probability_by_case(9, 1.0, 1.0, 90, "GK") == 0.0
    assert dc_point_probability_by_case(9, 0.0, 0.0, 0, "DEF") == 0.0
    # full-game minutes are clamped to 60-90 whatever the minutes model says
    assert dc_point_probability_by_case(9, 1.0, 1.0, 200, "DEF") == pytest.approx(_poisson_sf(10, 9.0))
    mid = dc_point_probability_by_case(11, 1.0, 1.0, 90, "MID")
    assert mid == pytest.approx(_poisson_sf(12, 11.0))


def test_fit_sizes_reads_overdispersion():
    rows = []
    for el, counts in ((1, [4, 12] * 10), (2, [6, 10] * 10)):
        rows += [{"position": "DEF", "minutes": 90, "element": el, "dc": c} for c in counts]
    rows += [{"position": "MID", "minutes": 90, "element": 3, "dc": c} for c in [2, 16] * 10]
    rows += [{"position": "DEF", "minutes": 30, "element": 1, "dc": 40}]   # not a full game
    sizes = dc.fit_sizes(rows)
    assert sizes["MID"] == sizes["FWD"] and sizes["DEF"] > sizes["MID"] > 0
    m, v = 8.0, 16 * 20 / 19                                              # player 1's moments
    assert math.isfinite(sizes["DEF"]) and v > m


def test_brier_and_compare():
    a = dc.brier_by_gw([(2, 1, 5, "DEF", 0.1, 1), (2, 2, 6, "MID", 0.2, 0), (2, 3, 7, "GK", 0.0, 0)], "s")
    b = dc.brier_by_gw([(2, 1, 5, "DEF", 0.5, 1), (2, 2, 6, "MID", 0.2, 0)], "s")
    assert a[("s", 2)]["n"] == 2                       # keepers are not scored
    r = dc.compare_brier(a, b)
    assert r["brier_a"] == pytest.approx((0.81 + 0.04) / 2) and r["diff"] < 0
    assert r["calibration_b"]["DEF"]["expected"] == pytest.approx(1.0)
    with pytest.raises(ValueError):
        dc.compare_brier(a, dc.brier_by_gw([(2, 9, 5, "DEF", 0.5, 1), (2, 2, 6, "MID", 0.2, 0)], "s"))


def test_verdict():
    assert dc.verdict({"ci": [-0.01, -0.001]}, {"ci": [-0.001, 0.01]}) == "SHIP"
    assert dc.verdict({"ci": [-0.01, 0.001]}, {"ci": [-0.001, 0.01]}) == "INCONCLUSIVE"
    assert dc.verdict({"ci": [0.001, 0.01]}, {"ci": [0.0, 0.01]}) == "DO NOT SHIP"
