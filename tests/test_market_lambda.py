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


# --- the upcoming-fixtures fetch: a BOM cost four months of market lambdas ---------------- #
class _CsvResp:
    """Mimics what `requests` hands back for football-data's CSVs: raw bytes, and a `.text`
    decoded as ISO-8859-1 because the server declares no charset for `text/csv`."""

    status_code = 200

    def __init__(self, content: bytes):
        self.content = content

    @property
    def text(self) -> str:
        return self.content.decode("iso-8859-1")

    def raise_for_status(self):
        return None


_FIXTURES_CSV = (
    "Div,Date,Time,HomeTeam,AwayTeam,AvgH,AvgD,AvgA,Avg>2.5,Avg<2.5\n"
    "B1,21/08/2026,19:45,Standard,RAAL La Louviere,1.92,3.37,3.79,2.05,1.75\n"
    "E0,22/08/2026,15:00,Everton,Crystal Palace,2.23,3.40,3.24,1.93,1.83\n"
    "E0,22/08/2026,17:30,Man City,Bournemouth,1.25,6.20,11.50,1.50,2.55\n"
)


def _patch_fetch(monkeypatch, content: bytes):
    from fpledge.ingest import footballdata

    monkeypatch.setattr(footballdata, "get_with_retries",
                        lambda *a, **k: _CsvResp(content))
    monkeypatch.setattr(footballdata.landing, "land", lambda *a, **k: None)


def test_fetch_upcoming_survives_a_byte_order_mark(monkeypatch):
    """football-data's fixtures.csv starts with a UTF-8 BOM and is served with no charset, so
    `resp.text` decodes it as ISO-8859-1 and the first header field becomes `\xef\xbb\xbfDiv`.
    Every `row["Div"]` lookup then missed, `fetch_upcoming` returned [], and the market-lambda
    path — a validated +0.0085 Spearman — silently never ran in production. Only the FIRST
    column is affected, which is why `parse_csv` was fine and nothing failed.
    """
    from fpledge.ingest.footballdata import fetch_upcoming

    _patch_fetch(monkeypatch, b"\xef\xbb\xbf" + _FIXTURES_CSV.encode("utf-8"))
    got = fetch_upcoming()

    assert [m["home"] for m in got] == ["Everton", "Man City"]   # E0 only, BOM notwithstanding
    assert got[0]["o_h"] == 2.23 and got[0]["o_over"] == 1.93


def test_fetch_upcoming_without_a_bom_is_unchanged(monkeypatch):
    """The fix must not depend on the mark being there."""
    from fpledge.ingest.footballdata import fetch_upcoming

    _patch_fetch(monkeypatch, _FIXTURES_CSV.encode("utf-8"))
    assert len(fetch_upcoming()) == 2


def test_a_file_with_no_row_in_our_division_is_a_parse_failure(monkeypatch):
    """Empty must never be indistinguishable from blind. Out of season the file is empty and []
    is right; a file full of other divisions' fixtures and none of ours means the parse missed,
    and that has to raise rather than read as a quiet week."""
    import pytest

    from fpledge.ingest.footballdata import fetch_upcoming

    only_belgium = (
        "Div,Date,Time,HomeTeam,AwayTeam,AvgH,AvgD,AvgA,Avg>2.5,Avg<2.5\n"
        "B1,21/08/2026,19:45,Standard,RAAL La Louviere,1.92,3.37,3.79,2.05,1.75\n"
    )
    _patch_fetch(monkeypatch, only_belgium.encode("utf-8"))
    with pytest.raises(ValueError, match="parse failure"):
        fetch_upcoming()


def test_an_empty_file_still_returns_nothing(monkeypatch):
    """Out of season the file carries a header and no rows. That is genuinely empty."""
    from fpledge.ingest.footballdata import fetch_upcoming

    _patch_fetch(monkeypatch, b"Div,Date,HomeTeam,AwayTeam,AvgH,AvgD,AvgA,Avg>2.5,Avg<2.5\n")
    assert fetch_upcoming() == []


# --- the source chain: a free lead, a keyed standby --------------------------------------- #
_ROW = {"home": "Everton", "away": "Crystal Palace",
        "o_h": 2.23, "o_d": 3.40, "o_a": 3.24, "o_over": 1.93, "o_under": 1.83}


def test_football_data_leads_and_the_standby_is_not_called(monkeypatch):
    """The standby costs credits. It must not be touched on a week the free source answers."""
    from fpledge import gw

    called = []
    monkeypatch.setattr(gw.footballdata, "fetch_upcoming", lambda: [_ROW])
    monkeypatch.setattr(gw.oddsapi, "upcoming_1x2_ou", lambda: called.append(1) or [])

    rows, source, errors = gw._upcoming_odds()
    assert source == "football_data" and rows == [_ROW] and errors == {}
    assert called == []


def test_an_outage_falls_through_to_the_standby(monkeypatch):
    """football-data returned 503 for three days across 2026-09-06..09. A validated input with
    one point of failure spends those days silently degraded."""
    from fpledge import gw

    def _boom():
        raise RuntimeError("503 Server Error")

    monkeypatch.setattr(gw.footballdata, "fetch_upcoming", _boom)
    monkeypatch.setattr(gw.oddsapi, "upcoming_1x2_ou", lambda: [_ROW])

    rows, source, errors = gw._upcoming_odds()
    assert source == "the_odds_api" and rows == [_ROW]
    assert "503" in errors["football_data"]        # why the lead was skipped, not just that


def test_both_sources_down_reports_both_reasons(monkeypatch):
    """No odds is a supported state — it must never fail the precompute. It must also never be
    silent about which sources were asked and what each said."""
    from fpledge import gw
    from fpledge.ingest.oddsapi import NoApiKey

    def _boom():
        raise RuntimeError("503 Server Error")

    def _nokey():
        raise NoApiKey("no key")

    monkeypatch.setattr(gw.footballdata, "fetch_upcoming", _boom)
    monkeypatch.setattr(gw.oddsapi, "upcoming_1x2_ou", _nokey)

    rows, source, errors = gw._upcoming_odds()
    assert rows == [] and source == "none"
    assert set(errors) == {"football_data", "the_odds_api"}

    mapping, report = gw._market_lambda_map({1: "Everton", 2: "Crystal Palace"})
    assert mapping == {} and report["mapped"] == 0
    assert report["source"] == "none" and report["errors"] == errors


def test_the_report_names_the_source_that_actually_priced_the_week(monkeypatch):
    """`meta.market` is how a reader tells a market-priced artifact from an engine-only one."""
    from fpledge import gw

    monkeypatch.setattr(gw.footballdata, "fetch_upcoming", lambda: [_ROW])
    mapping, report = gw._market_lambda_map({7: "Everton", 8: "Crystal Palace"})

    assert report["source"] == "football_data"
    assert report["fixtures_with_odds"] == 1 and report["mapped"] == 1
    assert list(mapping) == [(7, 8)]
    lam_home, lam_away = mapping[(7, 8)]
    assert 0.05 < lam_home < 6.0 and 0.05 < lam_away < 6.0
