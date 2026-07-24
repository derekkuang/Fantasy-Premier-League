"""De-vig + CLV correctness — the betting layer's honesty depends on these."""

import math

from fpledge.betting import odds


THREE_WAY = [2.10, 3.50, 3.80]  # a typical 1X2 market (overround > 1)


def test_overround_present():
    assert odds.overround(THREE_WAY) > 1.0


def test_proportional_devig_sums_to_one():
    q = odds.proportional_devig(THREE_WAY)
    assert math.isclose(sum(q), 1.0, abs_tol=1e-12)
    assert all(0.0 < p < 1.0 for p in q)


def test_shin_devig_sums_to_one_and_removes_vig():
    q = odds.shin_devig(THREE_WAY)
    assert math.isclose(sum(q), 1.0, abs_tol=1e-9)
    assert all(0.0 < p < 1.0 for p in q)
    # De-vigged favourite prob must be below the raw (vig-inflated) implied prob.
    assert q[0] < odds.implied_prob(THREE_WAY[0])


def test_no_vig_market_passthrough():
    # A fair market (sums to exactly 1) should be returned ~unchanged.
    fair = [2.0, 2.0]
    q = odds.proportional_devig(fair)
    assert math.isclose(q[0], 0.5, abs_tol=1e-12)


def test_clv_sign():
    # Took 2.10, closed at 2.00 -> you beat the close (positive CLV).
    assert odds.closing_line_value(2.10, 2.00) > 0
    assert odds.closing_line_value(1.90, 2.00) < 0
