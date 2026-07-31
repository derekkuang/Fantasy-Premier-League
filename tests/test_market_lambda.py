"""Odds -> lambda inversion: de-vigged 1X2 + O/U 2.5 back into per-team expected goals."""

from fpledge.betting.market_lambda import _p_over_25, _solve_mu, market_lambdas


def test_symmetric_odds_give_equal_lambdas():
    lh, la = market_lambdas(2.6, 3.4, 2.6, 1.9, 1.9)  # even match
    assert abs(lh - la) < 0.05


def test_home_favourite_has_higher_lambda():
    lh, la = market_lambdas(1.5, 4.2, 6.5, 1.9, 1.9)  # strong home favourite
    assert lh > la + 0.3


def test_lower_over_odds_mean_more_total_goals():
    goals = market_lambdas(2.6, 3.4, 2.6, 1.5, 2.6)     # low over-2.5 odds -> high P(over)
    fewer = market_lambdas(2.6, 3.4, 2.6, 2.6, 1.5)
    assert sum(goals) > sum(fewer)


def test_solve_mu_monotone_and_round_trips():
    assert _solve_mu(0.7) > _solve_mu(0.3)              # higher P(over) -> higher mu
    mu = _solve_mu(0.5)
    assert abs(_p_over_25(mu) - 0.5) < 1e-3             # inversion is self-consistent


def test_lambdas_are_positive_and_sane():
    lh, la = market_lambdas(1.9, 3.6, 4.2, 1.8, 2.0)
    assert 0.05 <= lh <= 6.0 and 0.05 <= la <= 6.0
