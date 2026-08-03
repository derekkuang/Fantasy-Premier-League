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


# --- the standardised risk band ------------------------------------------------------ #
def test_risk_tier_direction_and_bounds():
    """1 = template (safe/conventional) .. 5 = deep punt."""
    assert rank.risk_tier(60.0) == 1
    assert rank.risk_tier(0.3) == 5
    for own in (0.0, 1.9, 2.0, 6.9, 7.0, 14.9, 15.0, 29.9, 30.0, 100.0):
        assert 1 <= rank.risk_tier(own) <= 5


def test_risk_tier_is_monotonic_in_ownership():
    """More owned can never be MORE of a punt — a non-monotonic band would be nonsense."""
    tiers = [rank.risk_tier(o) for o in range(0, 101)]
    assert tiers == sorted(tiers, reverse=True)


def test_risk_tier_boundaries_are_inclusive_at_the_threshold():
    assert rank.risk_tier(30.0) == 1 and rank.risk_tier(29.99) == 2
    assert rank.risk_tier(15.0) == 2 and rank.risk_tier(14.99) == 3
    assert rank.risk_tier(7.0) == 3 and rank.risk_tier(6.99) == 4
    assert rank.risk_tier(2.0) == 4 and rank.risk_tier(1.99) == 5


def test_risk_tier_cut_points_match_the_published_ranges():
    """The frontend prints these thresholds as copy (BAND_RANGE in web/src/lib/risk.ts: "30%+",
    "15-30%", "7-15%", "2-7%", "under 2%"). They live in two languages, so nothing but a test
    stops rank.py drifting and leaving the legend quietly stating a threshold that isn't real."""
    assert [t[0] for t in rank.RISK_TIERS] == [30.0, 15.0, 7.0, 2.0, 0.0]
    assert [t[2] for t in rank.RISK_TIERS] == [
        "Template", "Popular", "Emerging", "Differential", "Deep punt",
    ]


def test_every_tier_has_a_label():
    labels = {rank.risk_label(t) for t in range(1, 6)}
    assert len(labels) == 5 and "" not in labels
    assert rank.risk_label(1) == "Template"
    assert rank.risk_label(5) == "Deep punt"


def test_risk_band_is_ownership_only_not_a_quality_score():
    """A 9-xP star and a 0.5-xP bench player on the same ownership share a band. The band
    says how contrarian a pick is; the xP floor is what says whether it is any good."""
    assert rank.risk_tier(3.0) == rank.risk_tier(3.0)
    assert rank.risk_tier(3.0) == 4  # 2-7% band
