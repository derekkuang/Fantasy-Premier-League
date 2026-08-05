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


# --- historical closing O/U, without which market lambdas cannot be backtested ------------ #
def test_parse_csv_carries_closing_over_under():
    """`market_lambdas` needs 1X2 AND over/under 2.5 — the 1X2 prices fix supremacy, the O/U
    fixes total goals, and neither alone determines a pair of lambdas. parse_csv carried only
    the 1X2 triple, so the market-lambda path shipped to production while being impossible to
    score against the engine on any historical season. These two fields are what make
    `validate_xp(fixture_lambdas=...)` measurable."""
    from fpledge.ingest.footballdata import parse_csv

    csv_text = (
        "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,PSCH,PSCD,PSCA,PC>2.5,PC<2.5\n"
        "E0,16/08/2024,Man United,Fulham,1,0,1.65,4.23,5.28,1.63,2.38\n"
    )
    rows = parse_csv(csv_text, "2024-25")
    assert len(rows) == 1
    r = rows[0]
    assert r["close_h"] == 1.65 and r["close_a"] == 5.28
    assert r["close_over25"] == 1.63
    assert r["close_under25"] == 2.38


def test_a_row_without_over_under_still_parses():
    """Older seasons and some divisions carry no O/U column. The match must still load for the
    engine fit — it simply cannot contribute a market lambda."""
    from fpledge.ingest.footballdata import parse_csv

    csv_text = (
        "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,PSCH,PSCD,PSCA\n"
        "E0,16/08/2024,Man United,Fulham,1,0,1.65,4.23,5.28\n"
    )
    rows = parse_csv(csv_text, "2024-25")
    assert len(rows) == 1
    assert rows[0]["close_over25"] is None
    assert rows[0]["home_goals"] == 1
