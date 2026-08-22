"""Current-season recency minutes reaching the SERVING path.

The gap these tests close: `validate_xp` — the harness behind every published accuracy number —
runs minutes_mode="recent", while production shipped `from_season` on last-season aggregates
all season long. From the first mid-season precompute onward, the model users saw was a
different, unmeasured model from the one the README describes. The wiring is: `pull_data`
lands `event/{gw}/live/` per finalised gameweek -> `recent_minutes_by_code` assembles per-player
lists -> `compute_xp_records` switches a player with enough evidence onto `from_recent`.

Preseason behaviour must be byte-identical to before the wiring existed — that is asserted,
not assumed.
"""

from __future__ import annotations

from fpledge.gw import recent_minutes_by_code
from fpledge.models.minutes import MinutesModel
from fpledge.models.xp_table import MIN_RECENT_GWS, compute_xp_records


# --- assembling per-player lists from landed event-live payloads --------------------------- #
def _live(*pairs):
    return {"elements": [{"id": el, "stats": {"minutes": m}} for el, m in pairs]}


ELEMENTS = [
    {"id": 11, "code": 1, "team": 1},
    {"id": 22, "code": 2, "team": 2},
]


def test_minutes_are_ordered_oldest_to_newest():
    live = {2: _live((11, 90)), 1: _live((11, 60)), 3: _live((11, 0))}
    fixtures = [(1, 1, 2), (2, 1, 2), (3, 1, 2)]
    assert recent_minutes_by_code(ELEMENTS, live, fixtures)[1] == [60, 90, 0]


def test_a_blank_gameweek_is_absent_not_a_zero():
    """Event-live reports 0 minutes both for 'benched' and for 'his club had no fixture'.
    A blank folded in as 0 would depress the recency estimate for no footballing reason —
    the backtest's lists only ever contain gameweeks the team actually played."""
    live = {1: _live((11, 90), (22, 90)), 2: _live((11, 0), (22, 85))}
    fixtures = [(1, 1, 2), (2, 2, 3)]        # GW2: team 1 blank, team 2 plays
    out = recent_minutes_by_code(ELEMENTS, live, fixtures)
    assert out[1] == [90], "team 1's blank GW2 must not append a phantom 0"
    assert out[2] == [90, 85]


def test_an_unknown_element_is_skipped_not_guessed():
    live = {1: _live((99, 90))}
    assert recent_minutes_by_code(ELEMENTS, live, [(1, 1, 2)]) == {}


# --- the switch inside compute_xp_records -------------------------------------------------- #
class _FakeEngine:
    def knows(self, name):
        return True

    def predict(self, home, away):
        return type("P", (), {"lam_home": 1.4, "lam_away": 1.1,
                              "clean_sheet_home": 0.33, "clean_sheet_away": 0.25})()


def _player(**over):
    base = {
        "code": 1, "element_id": 11, "team_id": 1, "position": "MID", "web_name": "P",
        "minutes": 3000, "starts": 34, "xg": 8.0, "xa": 6.0, "dc": 40, "bonus": 12,
        "ownership": 20.0,
    }
    base.update(over)
    return base


def _record(recent_minutes=None, availability=None):
    recs, _, _ = compute_xp_records(
        [_player()], {1: "A", 2: "B"}, [(1, 2)], _FakeEngine(),
        {"A": "A", "B": "B"}, {1: 7.5},
        availability=availability, recent_minutes=recent_minutes,
    )
    return recs[0]


def test_enough_current_season_evidence_switches_to_the_recency_model():
    """A nailed-on starter last season (3000 minutes) who has been benched for six straight
    gameweeks must be projected on the bench he actually sits on, not last season's minutes."""
    benched = {1: [90, 20, 0, 0, 0, 0]}
    expected = MinutesModel().from_recent(benched[1][-6:]).x_minutes
    got = _record(recent_minutes=benched)["x_minutes"]
    assert got == expected
    assert got < _record()["x_minutes"], "recency evidence must override the season proxy"


def test_too_little_evidence_keeps_the_preseason_proxy():
    thin = {1: [90] * (MIN_RECENT_GWS - 1)}
    assert _record(recent_minutes=thin)["x_minutes"] == _record()["x_minutes"]


def test_an_all_zero_history_keeps_the_preseason_proxy():
    """THE FABRICATION GUARD. A backfilled event-live payload lists the CURRENT element set,
    so a player who was not yet in the game accrues a phantom all-zero history — enough
    gameweeks of it to cross MIN_RECENT_GWS and pin a healthy new signing to 0.00 xP, silently
    dropping him from every ranking and the optimiser pool. Zero appearances is not evidence
    about his minutes; the preseason proxy is the only informed estimate held."""
    fabricated = {1: [0] * 10}
    assert _record(recent_minutes=fabricated)["x_minutes"] == _record()["x_minutes"]


def test_a_zeroed_window_after_real_appearances_stays_on_the_recency_model():
    """The guard's boundary, stated so nobody 'fixes' it: a player who HAS played this season
    and then stopped (dropped, or out injured) keeps the recency model, and an all-zero window
    projects him at zero minutes. Those zeros are real selection decisions — and this is the
    validated configuration's behaviour, not a bug the guard missed."""
    stopped = {1: [90, 90, 0, 0, 0, 0, 0, 0]}
    assert _record(recent_minutes=stopped)["x_minutes"] == 0.0


def test_no_recent_minutes_is_byte_identical_to_before_the_wiring():
    """Preseason (nothing landed) and the argument omitted must be the SAME model — the
    regression this guards is the wiring itself changing a projection it has no data for."""
    assert _record(recent_minutes={}) == _record(recent_minutes=None) == _record()


def test_availability_still_applies_after_the_recency_switch():
    """The order is load-bearing (the backtest names it): availability discounts minutes
    BEFORE shares are built, whichever minutes model produced them."""
    nailed = {1: [90] * 6}
    rec = _record(recent_minutes=nailed, availability={1: (None, "i")})
    assert rec["x_minutes"] == 0.0 and rec["xp"] == 0.0


def test_only_the_last_six_gameweeks_are_read():
    """The harness scores from_recent on a[-6:]; a full-season list must not dilute it."""
    long_run = {1: [0] * 20 + [90] * 6}
    expected = MinutesModel().from_recent([90] * 6).x_minutes
    assert _record(recent_minutes=long_run)["x_minutes"] == expected


# --- gameweek-partitioned landings list the same on both backends -------------------------- #
def test_list_partitions_finds_gameweek_partitions_on_local_disk(tmp_path, monkeypatch):
    """The local glob must be recursive: single-level, a season-wide listing missed
    gw-partitioned objects that S3's prefix scan found — every laptop run read 'no event-live
    landed' while the cloud read the data, in the one function whose docstring says the
    backends cannot be allowed to drift."""
    from fpledge.ingest import landing

    monkeypatch.setattr("fpledge.config.RAW_DIR", tmp_path)
    monkeypatch.setattr("fpledge.config.RAW_URI", "")
    landing._backend = None
    try:
        landing.land({"elements": []}, source="fpl_api", endpoint="event_live", gameweek=7)
        season_wide = landing.list_partitions("fpl_api", "event_live")
        assert len(season_wide) == 1, "a season-wide listing must see gw-partitioned objects"
        assert landing.gameweek_of(season_wide[0]) == 7
        assert landing.list_partitions("fpl_api", "event_live", gameweek=7) == season_wide
        assert landing.list_partitions("fpl_api", "event_live", gameweek=8) == []
    finally:
        landing._backend = None


def test_landed_event_live_reads_only_gameweeks_inside_the_bound(tmp_path, monkeypatch):
    """`max_gw` is the point-in-time rule at the read layer: predicting gameweek N passes N-1,
    so a re-precompute of an early week neither sees nor fetches payloads that postdate its
    own deadline."""
    from fpledge.ingest import landing
    from fpledge.storage.load import landed_event_live

    monkeypatch.setattr("fpledge.config.RAW_DIR", tmp_path)
    monkeypatch.setattr("fpledge.config.RAW_URI", "")
    landing._backend = None
    try:
        for gw in (1, 2, 3):
            landing.land({"gw": gw}, source="fpl_api", endpoint="event_live", gameweek=gw)
        assert landed_event_live(max_gw=2) == {1: {"gw": 1}, 2: {"gw": 2}}
        assert landed_event_live(max_gw=0) == {}
        assert set(landed_event_live()) == {1, 2, 3}
    finally:
        landing._backend = None
