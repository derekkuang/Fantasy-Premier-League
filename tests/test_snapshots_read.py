"""Reading pre-deadline snapshots back for the backtest.

There is no real snapshot data yet — capture starts 2026-08-21 — so these tests drive the reader
against synthetic captures. That is the point: the plumbing has to be correct BEFORE a season of
data exists, because the data cannot be recaptured and the first person to use it will be
reading numbers, not reviewing code.

The rule that matters most is the timing one. A snapshot taken after the deadline has seen the
team sheet, so scoring against it manufactures accuracy that cannot be reproduced live — the same
class of error as §16's contaminated baseline, in a new place.
"""

from __future__ import annotations

import gzip
import json

import pytest

from fpledge.eval.snapshots import (
    availability_map,
    best_capture_per_gameweek,
    coverage,
    load_index,
)


def _capture(tmp_path, gw, hours_before, players, ts="20260821T140000Z"):
    """Write a synthetic bootstrap capture and return its index row."""
    p = tmp_path / f"bootstrap_snapshot_gw{gw}_{ts}.json.gz"
    with gzip.open(p, "wt", encoding="utf-8") as fh:
        json.dump({"elements": players}, fh)
    return {
        "ingest_ts": ts,
        "for_gameweek": gw,
        "hours_before_deadline": hours_before,
        "n_players": len(players),
        "paths": [str(p)],
    }


def _player(pid, chance=None, status="a", ep="4.5"):
    return {"id": pid, "chance_of_playing_next_round": chance, "status": status, "ep_next": ep}


# --- the timing rule --------------------------------------------------------------------- #
def test_a_capture_taken_after_the_deadline_is_refused():
    """It has seen the team sheet. Using it would leak the answer into a validation number."""
    idx = [{"for_gameweek": 1, "hours_before_deadline": -2.0, "paths": []}]
    assert best_capture_per_gameweek(idx) == {}


def test_a_capture_at_exactly_the_deadline_is_refused():
    idx = [{"for_gameweek": 1, "hours_before_deadline": 0.0, "paths": []}]
    assert best_capture_per_gameweek(idx) == {}


def test_the_latest_pre_deadline_capture_wins():
    """Closest to the deadline is the most informed and is still a forecast."""
    idx = [
        {"for_gameweek": 1, "hours_before_deadline": 48.0, "ingest_ts": "early", "paths": []},
        {"for_gameweek": 1, "hours_before_deadline": 3.0, "ingest_ts": "late", "paths": []},
        {"for_gameweek": 1, "hours_before_deadline": 12.0, "ingest_ts": "mid", "paths": []},
    ]
    assert best_capture_per_gameweek(idx)[1]["ingest_ts"] == "late"


def test_a_post_deadline_capture_never_displaces_a_valid_one():
    idx = [
        {"for_gameweek": 1, "hours_before_deadline": 5.0, "ingest_ts": "good", "paths": []},
        {"for_gameweek": 1, "hours_before_deadline": -1.0, "ingest_ts": "too late", "paths": []},
    ]
    assert best_capture_per_gameweek(idx)[1]["ingest_ts"] == "good"


def test_rows_without_timing_information_are_refused():
    idx = [{"for_gameweek": 1, "paths": []}, {"hours_before_deadline": 3.0, "paths": []}]
    assert best_capture_per_gameweek(idx) == {}


# --- reading the payload ----------------------------------------------------------------- #
def test_availability_map_preserves_fpl_semantics(tmp_path):
    """chance_of_playing stays a percentage-or-None because that is precisely what
    `models.minutes.availability_factor` consumes — the backtest must apply the identical
    function production applies, not a reinterpretation of it."""
    idx = [_capture(tmp_path, 1, 3.0, [
        _player(10, chance=None, status="a", ep="5.1"),
        _player(11, chance=75, status="d"),
        _player(12, chance=0, status="i"),
    ])]
    av = availability_map(idx)
    assert av[(1, 10)] == {"chance_of_playing": None, "status": "a", "ep_next": 5.1}
    assert av[(1, 11)]["chance_of_playing"] == 75.0
    assert av[(1, 12)]["status"] == "i"


def test_a_missing_or_null_status_reads_as_available(tmp_path):
    """FPL omits `status` for fit players in some payload versions. It must become 'a', not
    None: `availability_factor` maps unknown statuses to a 1.0 multiplier either way, but only
    'a' round-trips as the thing FPL actually means, and a None would quietly become a magic
    value if anyone later switched on strict status handling."""
    idx = [_capture(tmp_path, 1, 3.0, [
        {"id": 20, "chance_of_playing_next_round": None, "ep_next": "4.0"},   # no status key
        {"id": 21, "chance_of_playing_next_round": None, "status": None, "ep_next": "4.0"},
    ])]
    av = availability_map(idx)
    assert av[(1, 20)]["status"] == "a"
    assert av[(1, 21)]["status"] == "a"


def test_a_zero_chance_survives_as_zero_not_as_missing(tmp_path):
    """0 is falsy in Python and means "certainly out" in FPL. A `or None` anywhere in this path
    would turn the most decisive value in the feed into no information at all."""
    idx = [_capture(tmp_path, 1, 3.0, [_player(30, chance=0, status="d")])]
    assert availability_map(idx)[(1, 30)]["chance_of_playing"] == 0.0


def test_missing_files_are_skipped_rather_than_raising(tmp_path):
    idx = [{"for_gameweek": 1, "hours_before_deadline": 3.0,
            "paths": [str(tmp_path / "gone.json.gz")]}]
    assert availability_map(idx) == {}


def test_load_index_on_a_missing_file_is_empty_not_an_error(tmp_path):
    assert load_index(tmp_path / "never_ran.jsonl") == []


def test_coverage_reports_the_gameweeks_it_does_not_have():
    """The §13 lesson, applied pre-emptively: a metric averaged over gameweeks the feature only
    partly covers is not the metric it claims to be, so the gap has to be visible."""
    av = {(9, 1): {}, (9, 2): {}, (11, 1): {}}
    c = coverage(av, range(9, 14))
    assert c["gameweeks_wanted"] == 5
    assert c["gameweeks_covered"] == 2
    assert c["missing"] == [10, 12, 13]
    assert c["share"] == 0.4


# --- the backtest hook ------------------------------------------------------------------- #
pytest.importorskip("numpy")
pytest.importorskip("scipy")

from fpledge.eval.fpl_backtest import validate_xp
from tests.test_fpl_backtest import _synthetic


def test_availability_scales_projections_and_absence_leaves_them_alone():
    rows, fixtures, teams = _synthetic()
    _, base = validate_xp(rows, fixtures, teams, burn_in=2, min_rate_minutes=90,
                          return_records=True)
    b = {(g, el): my for (g, el, my, *_) in base}

    # an empty map must change nothing at all
    _, empty = validate_xp(rows, fixtures, teams, burn_in=2, min_rate_minutes=90,
                           availability={}, return_records=True)
    assert b == {(g, el): my for (g, el, my, *_) in empty}

    # Ruling a player out zeroes him AND lifts his clubmates: his share of the team's goals is
    # redistributed, which is the whole reason availability has to be applied before shares are
    # allocated. Players at other clubs must be untouched.
    ruled_out = {(g, 101): {"chance_of_playing": 0.0, "status": "i"} for g in range(1, 7)}
    _, out = validate_xp(rows, fixtures, teams, burn_in=2, min_rate_minutes=90,
                         availability=ruled_out, return_records=True)
    o = {(g, el): my for (g, el, my, *_) in out}
    assert all(o[k] == 0.0 for k in o if k[1] == 101)

    clubmates = [k for k in o if k[1] in (102, 103)]        # team A outfielders
    other_club = [k for k in o if k[1] in (201, 202, 203, 204)]
    assert clubmates and other_club
    assert any(o[k] > b[k] for k in clubmates), "a ruled-out player's share must redistribute"
    assert all(o[k] == b[k] for k in other_club), "another club must be unaffected"


def test_a_doubtful_player_is_discounted_not_removed():
    rows, fixtures, teams = _synthetic()
    _, base = validate_xp(rows, fixtures, teams, burn_in=2, min_rate_minutes=90,
                          return_records=True)
    doubt = {(g, 103): {"chance_of_playing": 50.0, "status": "d"} for g in range(1, 7)}
    _, half = validate_xp(rows, fixtures, teams, burn_in=2, min_rate_minutes=90,
                          availability=doubt, return_records=True)
    b = {(g, el): my for (g, el, my, *_) in base}
    h = {(g, el): my for (g, el, my, *_) in half}
    target = [k for k in b if k[1] == 103]
    assert target
    assert all(0 < h[k] < b[k] for k in target)
