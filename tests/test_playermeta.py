"""Per-player context parsed from the bootstrap blob.

The point of these fields is EXPLANATORY — they must never move a projection. The tests that
matter here are the parsing edge cases (FPL sends numbers as strings, and nulls freely) and
the invariant that `availability.factor` equals what the minutes model actually applied.
"""

from __future__ import annotations

import pytest

from fpledge.models.minutes import MinutesModel, MinutesPrediction, availability_factor
from fpledge.models.xp_table import compute_xp_records
from fpledge.playermeta import EMPTY_META, player_meta


def _el(code, **over):
    base = {
        "code": code, "status": "a", "chance_of_playing_next_round": None,
        "news": "", "news_added": None, "form": "0.0", "points_per_game": "4.4",
        "ep_next": "4.0", "cost_change_event": 0, "cost_change_start": 0,
        "transfers_in_event": 0, "transfers_out_event": 0,
        "penalties_order": None, "corners_and_indirect_freekicks_order": None,
        "direct_freekicks_order": None,
    }
    base.update(over)
    return base


def test_available_player_is_unflagged_and_unscaled():
    m = player_meta({"elements": [_el(1)]})[1]
    assert m["availability"]["status"] == "a"
    assert m["availability"]["label"] == "available"
    assert m["availability"]["factor"] == 1.0
    assert m["availability"]["news"] == ""


def test_injured_player_carries_reason_and_zero_factor():
    m = player_meta({"elements": [
        _el(1, status="i", chance_of_playing_next_round=0,
            news="Groin injury - Expected back 21 Aug", news_added="2026-07-20T10:00:00Z"),
    ]})[1]
    assert m["availability"]["factor"] == 0.0
    assert m["availability"]["label"] == "injured"
    assert "Groin injury" in m["availability"]["news"]
    assert m["availability"]["news_added"] == "2026-07-20T10:00:00Z"


def test_doubtful_player_factor_matches_chance():
    m = player_meta({"elements": [_el(1, status="d", chance_of_playing_next_round=75)]})[1]
    assert m["availability"]["factor"] == 0.75
    assert m["availability"]["label"] == "doubtful"


def test_factor_is_exactly_what_the_minutes_model_applies():
    """The whole reason to surface `factor`: it must explain the projection, not approximate
    it. If these ever diverge the UI would be attributing a discount that didn't happen."""
    for status, chance in [("a", None), ("d", 75), ("i", 0), ("s", None), (None, 25)]:
        meta = player_meta({"elements": [
            _el(1, status=status, chance_of_playing_next_round=chance)
        ]})[1]
        base = MinutesPrediction(p_play=1.0, p_60=1.0, x_minutes=90.0)
        applied = MinutesModel().apply_availability(base, chance, status)
        assert meta["availability"]["factor"] == availability_factor(chance, status)
        assert applied.x_minutes == 90.0 * meta["availability"]["factor"]


def test_numeric_strings_and_nulls_parse():
    m = player_meta({"elements": [
        _el(1, form="3.7", points_per_game="5.2", ep_next=None),
    ]})[1]
    assert m["recent"]["form"] == 3.7
    assert m["recent"]["points_per_game"] == 5.2
    assert m["recent"]["ep_next"] is None  # absent, not silently 0.0 — 0.0 is a real forecast


def test_empty_string_numerics_do_not_crash():
    m = player_meta({"elements": [_el(1, form="", points_per_game="")]})[1]
    assert m["recent"]["form"] == 0.0
    assert m["recent"]["points_per_game"] == 0.0


def test_price_deltas_convert_tenths_to_millions():
    m = player_meta({"elements": [
        _el(1, cost_change_event=1, cost_change_start=-3,
            transfers_in_event=50_000, transfers_out_event=12_000),
    ]})[1]
    assert m["price_moves"]["change_event"] == 0.1
    assert m["price_moves"]["change_start"] == -0.3
    assert m["price_moves"]["net_transfers"] == 38_000


def test_set_piece_orders_pass_through():
    m = player_meta({"elements": [
        _el(1, penalties_order=1, corners_and_indirect_freekicks_order=2),
    ]})[1]
    assert m["set_pieces"]["penalties"] == 1
    assert m["set_pieces"]["corners"] == 2
    assert m["set_pieces"]["freekicks"] is None


class _FakeEngine:
    def knows(self, name):
        return True

    def predict(self, home, away):
        return type("P", (), {"lam_home": 1.4, "lam_away": 1.1,
                              "clean_sheet_home": 0.33, "clean_sheet_away": 0.25})()


def _records(meta):
    player = {
        "code": 1, "element_id": 11, "team_id": 1, "position": "MID", "web_name": "P",
        "minutes": 2700, "starts": 30, "xg": 8.0, "xa": 6.0, "dc": 40, "bonus": 12,
        "ownership": 20.0,
    }
    recs, _, _ = compute_xp_records(
        [player], {1: "A", 2: "B"}, [(1, 2)], _FakeEngine(),
        {"A": "A", "B": "B"}, {1: 7.5}, meta=meta,
    )
    return recs[0]


def test_meta_never_overwrites_a_core_record_field():
    """The bundle is spread onto the record dict LAST, so any shared key silently replaces the
    record's own value. `price` (cost in £m) vs price momentum was exactly that collision, and
    it would have turned every player's price into a dict."""
    meta = player_meta({"elements": [_el(1, cost_change_event=3)]})
    with_meta, without = _records(meta), _records(None)

    assert with_meta["price"] == 7.5, "player cost must survive the meta spread"
    for key, value in without.items():
        if key in EMPTY_META:
            continue  # the bundle itself is expected to differ
        assert with_meta[key] == value, f"meta changed the projection field {key!r}"


def test_meta_attaches_context_without_moving_xp():
    """Availability already reached the projection through the minutes model; this layer is
    descriptive only and must not double-apply anything."""
    meta = player_meta({"elements": [_el(1, status="d", chance_of_playing_next_round=50)]})
    assert _records(meta)["xp"] == _records(None)["xp"]
    assert _records(meta)["availability"]["factor"] == 0.5


def test_template_risk_is_the_mirror_of_diff_value():
    r = _records(None)
    assert r["diff_value"] + r["template_risk"] == pytest.approx(r["xp"])


def test_empty_meta_matches_the_real_shape():
    """A record for a player missing from the bootstrap must have the same keys as one that
    is present, so the frontend never null-checks a whole branch."""
    real = player_meta({"elements": [_el(1)]})[1]
    assert real.keys() == EMPTY_META.keys()
    for k in real:
        assert real[k].keys() == EMPTY_META[k].keys()
