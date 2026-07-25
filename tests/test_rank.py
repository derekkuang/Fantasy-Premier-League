"""Rank-relative valuation: EO, differential value, and captain-for-rank."""

from fpledge.models import rank


def test_effective_ownership_bounds():
    assert rank.effective_ownership(0) == 0.0
    assert rank.effective_ownership(150) == 1.0        # clamps captain-inflated EO
    assert abs(rank.effective_ownership(29.3) - 0.293) < 1e-9


def test_differential_value_rewards_low_ownership():
    assert rank.differential_value(5.0, 0.1) > rank.differential_value(5.0, 0.8)


def test_template_and_differential_split_the_xp():
    xp, eo = 5.0, 0.6
    assert abs(rank.differential_value(xp, eo) + rank.template_risk(xp, eo) - xp) < 1e-9


def test_captain_score_prefers_differential_at_equal_xp():
    assert rank.captain_rank_score(6.0, 0.2) > rank.captain_rank_score(6.0, 0.7)
