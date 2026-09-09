"""True FDR: expected goals mapped to a 1 (easy) .. 5 (hard) scale, correct direction."""

from fpledge.fdr import attack_fdr, defence_fdr, fixture_ticker


class _FakeEngine:
    def knows(self, name):
        return True

    def predict(self, home, away):
        return type("P", (), {"lam_home": 1.0, "lam_away": 1.0,
                              "clean_sheet_home": 0.37, "clean_sheet_away": 0.37})()


def test_attack_fdr_direction_and_bounds():
    assert attack_fdr(2.5) < attack_fdr(1.0)     # more expected goals-for = easier attack
    assert 1 <= attack_fdr(1.5) <= 5


def test_defence_fdr_direction_and_bounds():
    assert defence_fdr(0.7) < defence_fdr(2.0)   # fewer expected goals-against = easier CS
    assert 1 <= defence_fdr(1.2) <= 5


def test_fixture_ticker_uses_market_lambdas_when_present():
    fpl_teams = {1: "Arsenal", 2: "Chelsea"}
    tmap = {"Arsenal": "Arsenal", "Chelsea": "Chelsea"}
    fixtures = [{"gw": 1, "home_id": 1, "away_id": 2}]

    engine_only = fixture_ticker(_FakeEngine(), fixtures, fpl_teams, tmap, start_gw=1, horizon=1)
    assert engine_only[1][0]["source"] == "model"
    assert engine_only[1][0]["lam_for"] == 1.0

    market = fixture_ticker(
        _FakeEngine(), fixtures, fpl_teams, tmap, start_gw=1, horizon=1,
        market_lambdas={(1, 2): (2.5, 0.5)},
    )
    home, away = market[1][0], market[2][0]
    assert home["source"] == "market" and away["source"] == "market"
    assert home["lam_for"] == 2.5 and home["lam_against"] == 0.5   # market lambdas drive the row
    assert away["lam_for"] == 0.5                                   # opponent's side mirrors
    # more expected goals-for than the engine's 1.0 -> easier attack FDR
    assert home["attack_fdr"] < engine_only[1][0]["attack_fdr"]


def test_a_team_blank_for_the_whole_window_still_gets_a_row():
    """Absence of fixtures is not absence of the team.

    The ticker used to be keyed only by teams that appeared in a fixture, so a club blank for
    the entire horizon vanished from `/fixtures/{gw}` and therefore from the grid — the same
    class of bug as a client-side truncation being blamed on the payload. The UI already draws
    an empty row (its rank key sinks one to the bottom); only the backend could not emit one.
    """
    fpl_teams = {1: "Arsenal", 2: "Chelsea", 3: "Everton"}
    tmap = {"Arsenal": "Arsenal", "Chelsea": "Chelsea", "Everton": "Everton"}
    fixtures = [{"gw": 1, "home_id": 1, "away_id": 2}]   # Everton plays nobody

    ticker = fixture_ticker(_FakeEngine(), fixtures, fpl_teams, tmap, start_gw=1, horizon=1)

    assert set(ticker) == {1, 2, 3}
    assert ticker[3] == []
    assert len(ticker[1]) == 1 and len(ticker[2]) == 1
