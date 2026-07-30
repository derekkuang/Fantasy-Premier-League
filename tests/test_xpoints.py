"""Expected-points components: bonus + Defensive-Contribution (Poisson-tail) modelling."""

from fpledge import config
from fpledge.models.xpoints import (
    PlayerContext,
    _poisson_sf,
    bonus_from_returns,
    dc_point_probability,
    expected_bonus,
    expected_conceded_penalty,
    expected_points,
    expected_points_breakdown,
)


def _ctx(pos, **kw):
    base = dict(
        position=pos, p_play=0.9, p_60=0.8, team_lambda=1.6,
        goal_share=0.15, assist_share=0.1, p_clean_sheet=0.35,
        x_saves=3.0, p_dc_point=0.4, x_bonus=0.5,
        opp_lambda=1.5, x_conceded_penalty=-0.4,
    )
    base.update(kw)
    return PlayerContext(**base)


def test_breakdown_terms_sum_to_total_and_match_expected_points():
    for pos in ("GK", "DEF", "MID", "FWD"):
        ctx = _ctx(pos)
        bd = expected_points_breakdown(ctx)
        term_sum = (
            bd["appearance"] + bd["goal_points"] + bd["assist_points"] + bd["cs_points"]
            + bd["conceded_points"] + bd["save_points"] + bd["dc_points"] + bd["bonus_points"]
        )
        assert term_sum == bd["total"]                       # the split is exact
        assert bd["total"] == expected_points(ctx)           # and matches the scalar API
        assert (bd["save_points"] > 0) == (pos == "GK")      # saves only for keepers
        assert (bd["conceded_points"] < 0) == (pos in ("GK", "DEF"))  # conceded penalty: GK/DEF only


def test_expected_conceded_penalty_sign_monotonicity_and_minutes():
    # always a non-positive penalty
    assert expected_conceded_penalty(1.5, 90) <= 0.0
    # a stronger opponent attack -> a bigger (more negative) expected penalty
    assert expected_conceded_penalty(2.2, 90) < expected_conceded_penalty(0.7, 90)
    # fewer minutes on the pitch -> smaller penalty (less negative)
    assert expected_conceded_penalty(1.5, 30) > expected_conceded_penalty(1.5, 90)
    # a clean-sheet-likely fixture is a small penalty, roughly -P(concede 2+) at full time
    assert -1.0 < expected_conceded_penalty(0.8, 90) < 0.0


def test_bonus_from_returns_tracks_returns_and_caps():
    assert bonus_from_returns(0.0, 0.0, 0.0, 0.0) == 0.0
    # more expected returns -> more expected bonus
    assert bonus_from_returns(0.8, 0.3, 0.4, 0.5) > bonus_from_returns(0.1, 0.0, 0.1, 0.0)
    # capped at the 3-point maximum
    assert bonus_from_returns(5.0, 5.0, 1.0, 1.0) == 3.0


def test_poisson_sf_basic():
    assert _poisson_sf(0, 5.0) == 1.0
    assert _poisson_sf(10, 12.0) > _poisson_sf(10, 6.0)   # higher mean -> fatter tail
    assert 0.0 <= _poisson_sf(10, 8.0) <= 1.0


def test_dc_probability_position_threshold_and_minutes():
    assert dc_point_probability(11.0, 90, "DEF") > dc_point_probability(4.0, 90, "DEF")
    assert 0.0 <= dc_point_probability(11.0, 90, "DEF") <= 1.0
    assert dc_point_probability(20.0, 90, "GK") == 0.0                      # no DC for GK
    # MID threshold (12) is harder than DEF (10) at the same per-90 rate
    assert dc_point_probability(9.0, 90, "MID") < dc_point_probability(9.0, 90, "DEF")
    # fewer minutes -> fewer expected actions -> lower probability
    assert dc_point_probability(11.0, 30, "DEF") < dc_point_probability(11.0, 90, "DEF")


def test_expected_bonus_scales_with_minutes():
    assert expected_bonus(1.0, 90) == 1.0
    assert expected_bonus(1.0, 45) == 0.5
    assert expected_bonus(-5.0, 90) == 0.0   # guard bad input


def test_bonus_and_dc_add_to_xp():
    kw = dict(
        position="MID", p_play=1.0, p_60=1.0, team_lambda=1.5,
        goal_share=0.0, assist_share=0.0, p_clean_sheet=0.0,
    )
    base = PlayerContext(**kw)
    plus = PlayerContext(x_bonus=0.7, p_dc_point=0.5, **kw)
    delta = expected_points(plus) - expected_points(base)
    assert abs(delta - (0.7 + 0.5 * config.DC_POINTS)) < 1e-9
