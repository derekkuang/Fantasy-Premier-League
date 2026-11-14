"""Predicted vs actual on the player sheet (fpledge/history.py)."""

from __future__ import annotations

import pytest

from fpledge.api import store
from fpledge.api.precompute import build_payload
from fpledge.history import player_history, published_in_window

DEADLINES = {1: "2026-08-21T17:30:00Z", 2: "2026-08-29T10:00:00Z", 3: "2026-09-05T10:00:00Z"}


TEAMS = {1: "Aston Villa", 2: "Chelsea", 3: "Fulham", 4: "Leeds"}
FIXTURES = {201: (1, 3), 202: (4, 1), 301: (2, 4)}      # fixture id -> (home, away)
CLUB_OF = {7: 1, 8: 1}                                  # both play for Villa today


def _history(published, live):
    return player_history(published, live, DEADLINES, FIXTURES, CLUB_OF, TEAMS)


def _artifact(run_ts, records):
    return {"meta": {"run_ts": run_ts}, "records": records}


def _rec(element_id, xp, team_id=1):
    return {"element_id": element_id, "xp": xp, "team_id": team_id}


def _live(*players, fixtures=(201,)):
    return {"elements": [{"id": el, "stats": {"total_points": pts, "minutes": mins},
                          "explain": [{"fixture": f, "stats": []} for f in fixtures]}
                         for el, pts, mins in players]}


# --- which projection counts -------------------------------------------------------------- #
def test_only_an_artifact_published_inside_its_own_window_counts():
    assert published_in_window(_artifact("2026-08-28T12:00:00Z", []), 2, DEADLINES)
    # rerun after the deadline: it could have seen the results
    assert not published_in_window(_artifact("2026-08-29T10:00:01Z", []), 2, DEADLINES)
    # before the previous deadline: last season's file under the same name
    assert not published_in_window(_artifact("2026-08-20T12:00:00Z", []), 2, DEADLINES)
    # gameweek 1 has no previous deadline, so it is bounded by age instead
    assert published_in_window(_artifact("2026-08-01T00:00:00Z", []), 1, DEADLINES)
    assert not published_in_window(_artifact("2025-12-01T00:00:00Z", []), 1, DEADLINES)
    assert not published_in_window({"meta": {}}, 2, DEADLINES)


def test_published_projection_sits_next_to_what_he_scored():
    published = {2: _artifact("2026-08-28T12:00:00Z", [_rec(7, 4.256)])}
    got = _history(published, {2: _live((7, 9, 90))})
    assert got[7] == [{"gw": 2, "xp": 4.26, "pts": 9, "mins": 90,
                       "vs": [{"opp": "Fulham", "home": True}], "as_club": None}]


def test_a_week_we_did_not_project_him_is_not_projected_never_zero():
    published = {2: _artifact("2026-08-28T12:00:00Z", [_rec(7, 4.0)])}
    got = _history(published, {2: _live((7, 2, 90), (8, 6, 90))})
    assert got[8] == [{"gw": 2, "xp": None, "pts": 6, "mins": 90,
                       "vs": [{"opp": "Fulham", "home": True}], "as_club": None}]


def test_a_rerun_after_the_deadline_is_not_shown_as_a_prediction():
    published = {2: _artifact("2026-08-30T08:00:00Z", [_rec(7, 4.0)])}
    got = _history(published, {2: _live((7, 9, 90))})
    assert got[7][0]["xp"] is None


def test_a_gameweek_with_no_artifact_still_shows_what_he_scored():
    got = _history({}, {3: _live((7, 1, 30))})
    assert got[7] == [{"gw": 3, "xp": None, "pts": 1, "mins": 30,
                       "vs": [{"opp": "Fulham", "home": True}], "as_club": None}]


def test_weeks_come_oldest_first_and_unfinalised_weeks_are_absent():
    published = {g: _artifact(ts, [_rec(7, float(g))])
                 for g, ts in ((1, "2026-08-20T00:00:00Z"), (2, "2026-08-28T00:00:00Z"))}
    live = {2: _live((7, 3, 90)), 1: _live((7, 5, 90))}           # GW3 not finalised yet
    got = _history(published, live)
    assert [e["gw"] for e in got[7]] == [1, 2]
    assert [e["xp"] for e in got[7]] == [1.0, 2.0]


def test_a_double_gameweek_lists_both_opponents_and_one_total():
    published = {2: _artifact("2026-08-28T12:00:00Z", [_rec(7, 8.5)])}
    got = _history(published, {2: _live((7, 14, 180), fixtures=(201, 202))})[7][0]
    assert got["vs"] == [{"opp": "Fulham", "home": True}, {"opp": "Leeds", "home": False}]
    assert (got["xp"], got["pts"], got["mins"]) == (8.5, 14, 180)


def test_the_opponent_is_the_real_one_and_a_wrong_club_projection_says_so():
    """The Jackson case: projected as a Chelsea player while he played for Villa."""
    published = {2: _artifact("2026-08-28T12:00:00Z", [_rec(7, 1.9, team_id=2)])}
    got = _history(published, {2: _live((7, 11, 85))})[7][0]
    assert got["vs"] == [{"opp": "Fulham", "home": True}]
    assert (got["xp"], got["as_club"]) == (1.9, "Chelsea")


def test_a_player_who_has_moved_since_gets_no_opponent_rather_than_a_guess():
    published = {2: _artifact("2026-08-28T12:00:00Z", [_rec(7, 3.0, team_id=2)])}
    got = _history(published, {2: _live((7, 2, 90), fixtures=(301,))})[7][0]  # Chelsea v Leeds
    assert (got["vs"], got["as_club"]) == ([], None)


def test_a_blank_week_has_no_opponent():
    got = _history({}, {2: _live((7, 0, 0), fixtures=())})[7][0]
    assert got["vs"] == [] and got["pts"] == 0


# --- wiring: the refresh attaches it, the detail endpoint serves it ------------------------- #
@pytest.fixture
def _serving_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("FPLEDGE_SERVING_DIR", str(tmp_path / "serving"))
    monkeypatch.delenv("FPLEDGE_SERVING_URI", raising=False)
    store.invalidate()
    yield
    store.invalidate()


def test_the_refresh_reads_the_stored_artifacts_users_saw(_serving_tmp, monkeypatch):
    store.write_gw(2, _artifact("2026-08-28T12:00:00Z", [_rec(7, 4.0)]))
    out = {
        "records": [{"element_id": 7, "xp": 5.0, "team_id": 1, "web_name": "p7",
                     "team_name": "Aston Villa", "position": "MID", "price": 5.0, "ownership": 1.0}],
        "matches": [], "fallback": [], "fpl_teams": TEAMS, "fixture_ticker": {},
        "source_report": {}, "live": {2: _live((7, 9, 90))}, "deadlines": DEADLINES,
        "fixture_teams": FIXTURES, "club_of": CLUB_OF,
    }
    monkeypatch.setattr("fpledge.api.precompute.assemble_for_serving", lambda gw, horizon=8: out)
    payload = build_payload(3, narrate=False)
    assert payload["records"][0]["history"] == [
        {"gw": 2, "xp": 4.0, "pts": 9, "mins": 90, "vs": [{"opp": "Fulham", "home": True}],
         "as_club": None}]
