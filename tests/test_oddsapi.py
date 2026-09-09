"""The Odds API client and the goalscorer capture.

No network. Everything is driven through a fake session, because the live path CANNOT be
exercised here — this was written without an API key, and the honest position is that the
offline behaviour is tested and the live request has never been made.

The failure this capture is most likely to suffer is silent: a wrong market key returns an empty
bookmaker list rather than an error, which is indistinguishable from "no book has priced it yet".
Several tests below exist only to make that loud.
"""

from __future__ import annotations

import pytest

from fpledge.ingest.oddsapi import (
    NoApiKey,
    OddsApiClient,
    OddsApiError,
    goalscorer_prices,
)


class _Resp:
    def __init__(self, payload, status=200, headers=None):
        self._payload = payload
        self.status_code = status
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _Session:
    def __init__(self, payload=None, status=200, headers=None):
        self.headers: dict = {}
        self.calls: list = []
        self._payload = payload if payload is not None else {}
        self._status = status
        # `is None`, not `or` — an explicitly EMPTY header dict is a case under test (some
        # responses carry no credit headers) and must not fall through to the defaults.
        self._headers = (
            {"x-requests-used": "12", "x-requests-remaining": "488"} if headers is None
            else headers
        )

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        return _Resp(self._payload, self._status, self._headers)


def _client(**kw):
    s = _Session(**kw)
    return OddsApiClient(api_key="k", session=s, min_interval=0), s


# --- the key, and refusing to look like a quiet week -------------------------------------- #
def test_a_missing_key_raises_rather_than_returning_empty():
    """An empty capture and a missing key must never be the same observation — one is a quiet
    week, the other is a week lost forever."""
    c = OddsApiClient(api_key="", session=_Session(), min_interval=0)
    with pytest.raises(NoApiKey):
        c.events()


def test_the_key_is_sent_as_a_query_parameter():
    c, s = _client(payload=[])
    c.events()
    assert s.calls[0][1]["apiKey"] == "k"


def test_out_of_credits_is_an_error_not_an_empty_result():
    c, _s = _client(payload={}, status=429)
    with pytest.raises(OddsApiError, match="429"):
        c.events()


def test_a_rejected_key_is_an_error():
    c, _s = _client(payload={}, status=401)
    with pytest.raises(OddsApiError, match="401"):
        c.events()


def test_a_transport_failure_is_an_odds_api_error_not_a_crash():
    """THE CRASH THIS PREVENTS. The capture's per-event loop catches OddsApiError so one failed
    fixture costs one fixture. A raw requests.Timeout is not OddsApiError: before the wrap it
    escaped that catch and crashed the run AFTER credits were spent, landing nothing and writing
    no index row — the exact 'credits spent, no evidence' state the index exists to prevent."""
    import requests

    class _TimeoutSession:
        def __init__(self):
            self.headers: dict = {}

        def get(self, url, params=None, timeout=None):
            raise requests.ReadTimeout("book hung")

    c = OddsApiClient(api_key="k", session=_TimeoutSession(), min_interval=0)
    with pytest.raises(OddsApiError, match="ReadTimeout"):
        c.events()


def test_a_5xx_is_an_odds_api_error_for_the_same_reason():
    """raise_for_status() throws requests.HTTPError, which the per-event catch would miss."""
    c, _s = _client(payload={}, status=500)
    with pytest.raises(OddsApiError, match="HTTP 500"):
        c.events()


def test_credit_headers_are_recorded():
    """The free tier is the entire premise, so the run has to report what it spent."""
    c, _s = _client(payload=[])
    c.events()
    assert c.credits_used == 12
    assert c.credits_remaining == 488


def test_missing_credit_headers_do_not_crash_the_capture():
    c, _s = _client(payload=[], headers={})
    c.events()
    assert c.credits_remaining is None


# --- request shape ------------------------------------------------------------------------ #
def test_event_odds_requests_the_market_and_region_it_was_asked_for():
    c, s = _client(payload={})
    c.event_odds("evt1", markets="player_goal_scorer_anytime", regions="uk")
    url, params = s.calls[0]
    assert url.endswith("/sports/soccer_epl/events/evt1/odds")
    assert params["markets"] == "player_goal_scorer_anytime"
    assert params["regions"] == "uk"
    assert params["oddsFormat"] == "decimal"


def test_list_markets_hits_the_markets_endpoint():
    c, s = _client(payload=[])
    c.list_markets("evt1")
    assert s.calls[0][0].endswith("/events/evt1/markets")


# --- flattening --------------------------------------------------------------------------- #
def _payload():
    return {
        "id": "evt1", "commence_time": "2026-08-22T14:00:00Z",
        "home_team": "Arsenal", "away_team": "Chelsea",
        "bookmakers": [
            {"key": "pinnacle", "markets": [
                {"key": "player_goal_scorer_anytime", "last_update": "2026-08-22T12:00:00Z",
                 "outcomes": [
                     {"description": "Bukayo Saka", "price": 3.1},
                     {"description": "Cole Palmer", "price": 3.8},
                 ]},
            ]},
            {"key": "betfair", "markets": [
                {"key": "player_goal_scorer_anytime",
                 "outcomes": [{"description": "Bukayo Saka", "price": 3.25}]},
            ]},
        ],
    }


def test_prices_flatten_with_the_context_needed_to_join_them_later():
    rows = goalscorer_prices(_payload())
    assert len(rows) == 3
    saka = [r for r in rows if r["player"] == "Bukayo Saka"]
    assert {r["bookmaker"] for r in saka} == {"pinnacle", "betfair"}
    assert saka[0]["home_team"] == "Arsenal"
    assert saka[0]["event_id"] == "evt1"


def test_prices_stay_decimal_odds_and_are_not_converted():
    """Converting means de-vigging, and a goalscorer market's overround runs 20-40% across a
    dozen-plus outcomes. `betting.odds` owns that choice; a capture records what was said so the
    modelling decision stays re-doable against the raw record."""
    rows = goalscorer_prices(_payload())
    assert {r["price"] for r in rows} == {3.1, 3.8, 3.25}
    assert all(r["price"] > 1.0 for r in rows)


def test_an_event_with_no_bookmakers_flattens_to_nothing_not_to_a_crash():
    assert goalscorer_prices({"id": "e", "bookmakers": []}) == []
    assert goalscorer_prices({}) == []


def test_outcome_name_is_used_when_description_is_absent():
    payload = {"id": "e", "bookmakers": [
        {"key": "b", "markets": [{"key": "m", "outcomes": [{"name": "Erling Haaland",
                                                            "price": 1.9}]}]},
    ]}
    assert goalscorer_prices(payload)[0]["player"] == "Erling Haaland"


# --- deadline selection, shared shape with snapshot.py ------------------------------------ #
import importlib.util
import pathlib

_spec = importlib.util.spec_from_file_location(
    "capture_props", pathlib.Path(__file__).resolve().parent.parent / "scripts" / "capture_props.py"
)
capture_props = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(capture_props)


def test_the_next_deadline_is_the_soonest_one_still_ahead():
    events = [
        {"id": 1, "deadline_time": "2026-08-14T17:30:00Z"},   # past
        {"id": 3, "deadline_time": "2026-08-28T17:30:00Z"},
        {"id": 2, "deadline_time": "2026-08-21T17:30:00Z"},   # the answer
    ]
    now = capture_props._parse("2026-08-20T00:00:00Z")
    gw, dt = capture_props.next_deadline(events, now)
    assert gw == 2
    assert dt.day == 21


def test_no_upcoming_deadline_returns_nothing_rather_than_the_last_one():
    """End of season. Filing a capture against a finished gameweek would look like evidence."""
    events = [{"id": 38, "deadline_time": "2026-05-24T14:00:00Z"}]
    now = capture_props._parse("2026-06-01T00:00:00Z")
    assert capture_props.next_deadline(events, now) == (None, None)


def test_unparseable_deadlines_are_skipped_not_guessed():
    events = [{"id": 1, "deadline_time": "not a date"},
              {"id": 2, "deadline_time": "2026-08-21T17:30:00Z"}]
    now = capture_props._parse("2026-08-01T00:00:00Z")
    assert capture_props.next_deadline(events, now)[0] == 2


# --- the gameweek-window filter: inverted once, never again ---------------------------------- #
def test_gameweek_fixtures_keeps_kickoffs_after_the_deadline():
    """THE BUG THIS PINS. The first version kept kickoffs BEFORE the deadline — backwards, since
    a gameweek's matches are what you set your team for ahead of its deadline — and captured
    zero prices for GW1 while exiting 0. Found only because the never-run script was proven by
    hand before being scheduled."""
    from datetime import UTC, datetime

    from scripts.capture_props import gameweek_fixtures

    deadline = datetime(2026, 8, 21, 17, 30, tzinfo=UTC)
    following = datetime(2026, 8, 28, 17, 30, tzinfo=UTC)
    events = [
        {"id": "past", "commence_time": "2026-08-20T19:00:00+00:00"},     # before the deadline
        {"id": "gw1a", "commence_time": "2026-08-21T19:00:00+00:00"},     # this gameweek
        {"id": "gw1b", "commence_time": "2026-08-23T15:00:00+00:00"},     # this gameweek
        {"id": "gw2", "commence_time": "2026-08-29T11:30:00+00:00"},      # after the NEXT deadline
    ]
    got = [e["id"] for e in gameweek_fixtures(events, deadline, following)]
    assert got == ["gw1a", "gw1b"]


def test_gameweek_fixtures_without_a_following_deadline_keeps_everything_after():
    from datetime import UTC, datetime

    from scripts.capture_props import gameweek_fixtures

    deadline = datetime(2026, 8, 21, 17, 30, tzinfo=UTC)
    events = [{"id": "a", "commence_time": "2026-08-22T14:00:00+00:00"},
              {"id": "b", "commence_time": "2026-09-30T14:00:00+00:00"}]
    assert len(gameweek_fixtures(events, deadline, None)) == 2


def test_gameweek_fixtures_drops_events_with_no_kickoff_time():
    from datetime import UTC, datetime

    from scripts.capture_props import gameweek_fixtures

    deadline = datetime(2026, 8, 21, 17, 30, tzinfo=UTC)
    assert gameweek_fixtures([{"id": "x"}], deadline, None) == []


# --- fixture-level 1X2 + O/U: the standby source for market lambdas ---------------------- #
def _event(home="Everton", away="Crystal Palace", books=2, line=2.5):
    """Two bookmakers, both pricing h2h and totals, with prices one apart so the mean is
    unambiguous."""
    return {
        "home_team": home, "away_team": away,
        "bookmakers": [
            {"key": f"book{i}", "markets": [
                {"key": "h2h", "outcomes": [
                    {"name": home, "price": 2.20 + i},
                    {"name": "Draw", "price": 3.40 + i},
                    {"name": away, "price": 3.20 + i},
                ]},
                {"key": "totals", "outcomes": [
                    {"name": "Over", "price": 1.90 + i, "point": line},
                    {"name": "Under", "price": 1.80 + i, "point": line},
                ]},
            ]}
            for i in range(books)
        ],
    }


def test_an_event_becomes_a_football_data_shaped_row():
    """The standby must be a drop-in: `gw._market_lambda_map` consumes both sources through the
    same keys, so a fallback week cannot change the shape of anything downstream."""
    from fpledge.ingest.oddsapi import _row_from_event

    row = _row_from_event(_event(books=1))
    assert set(row) == {"home", "away", "o_h", "o_d", "o_a", "o_over", "o_under"}
    assert row["home"] == "Everton" and row["away"] == "Crystal Palace"
    assert row["o_h"] == 2.20 and row["o_d"] == 3.40 and row["o_a"] == 3.20
    assert row["o_over"] == 1.90 and row["o_under"] == 1.80


def test_prices_are_averaged_across_bookmakers():
    """football-data's `Avg*` columns are averaged decimal odds, and those are the columns this
    project has always fed to `market_lambdas`. Matching that convention keeps a fallback week
    comparable to every other week."""
    from fpledge.ingest.oddsapi import _row_from_event

    row = _row_from_event(_event(books=2))
    assert row["o_h"] == 2.70      # mean(2.20, 3.20)
    assert row["o_over"] == 2.40   # mean(1.90, 2.90)


def test_an_event_missing_the_totals_line_is_dropped_not_half_used():
    """`market_lambdas` needs 1X2 AND over/under: the 1X2 prices fix supremacy, the totals fix
    total goals, and one without the other determines no pair of lambdas at all."""
    from fpledge.ingest.oddsapi import _row_from_event

    ev = _event(books=1)
    ev["bookmakers"][0]["markets"] = [ev["bookmakers"][0]["markets"][0]]   # h2h only
    assert _row_from_event(ev) is None


def test_a_totals_market_on_another_line_does_not_count():
    """Books price 1.5, 2.5 and 3.5. Only the 2.5 line inverts to the lambdas we want."""
    from fpledge.ingest.oddsapi import _row_from_event

    ev = _event(books=1, line=3.5)
    assert _row_from_event(ev) is None


def test_the_standby_raises_without_a_key_rather_than_reporting_a_quiet_week(monkeypatch):
    """The whole lesson of the football-data BOM: an empty return must never be the shape a
    configuration failure takes."""
    from fpledge.ingest.oddsapi import upcoming_1x2_ou

    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    with pytest.raises(NoApiKey):
        upcoming_1x2_ou()


def test_the_slate_costs_one_bulk_call_not_one_per_fixture(monkeypatch):
    """(markets x regions) credits for every fixture at once — 2, not 2 each. That is what lets
    these markets ride on the same free tier as the goalscorer capture."""
    from fpledge.ingest import oddsapi

    calls = []

    class _C:
        def sport_odds(self, markets, regions):
            calls.append((markets, regions))
            return [_event(), _event("Man City", "Bournemouth")]

    monkeypatch.setattr(oddsapi.landing, "land", lambda *a, **k: None)
    rows = oddsapi.upcoming_1x2_ou(client=_C())
    assert len(calls) == 1 and calls[0][0] == "h2h,totals"
    assert [r["home"] for r in rows] == ["Everton", "Man City"]
