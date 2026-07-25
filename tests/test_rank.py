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


def test_differential_captain_respects_xp_floor():
    # 9-xP template @85%, 8.5-xP mid @10%, 4.5-xP fringe @2%.
    xps = [9.0, 8.5, 4.5]
    eos = [0.85, 0.10, 0.02]
    # The fringe pick is below the 0.8*9=7.2 floor -> must NOT be chosen despite 2% ownership.
    assert rank.differential_captain_index(xps, eos, alpha=0.8) == 1


def test_differential_captain_can_be_the_top_pick():
    # Best xP is also low-owned; the only other option is below the floor.
    assert rank.differential_captain_index([9.0, 5.0], [0.10, 0.02], alpha=0.8) == 0


def test_differential_captain_empty():
    assert rank.differential_captain_index([], []) is None
