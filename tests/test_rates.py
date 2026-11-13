"""In-season player rates in production, and the current player list they need (HANDOFF §36)."""

from __future__ import annotations

import pytest

from fpledge.api.precompute import health_check
from fpledge.eval import player_rates as tested
from fpledge.gw import current_players, missing_gameweeks
from fpledge.models import rates
from fpledge.models.xp_table import LOW_COVERAGE, compute_xp_records


class _FakeEngine:
    def knows(self, name):
        return True

    def predict(self, home, away):
        return type("P", (), {"lam_home": 1.4, "lam_away": 1.1,
                              "clean_sheet_home": 0.33, "clean_sheet_away": 0.25})()


def _player(code, minutes, xg=0.0, xa=0.0, team_id=1, position="FWD", starts=None):
    return {"code": code, "element_id": code + 100, "team_id": team_id, "position": position,
            "web_name": str(code), "minutes": minutes, "starts": starts or minutes // 85,
            "xg": xg, "xa": xa, "dc": 0, "bonus": 0, "ownership": 5.0}


def _live(gw_stats):
    """{gw: payload} from {gw: {element_id: {stat: value}}}, shaped like FPL's event-live."""
    return {gw: {"elements": [{"id": el, "stats": s} for el, s in by_el.items()]}
            for gw, by_el in gw_stats.items()}


# --- the settings are the tested ones -------------------------------------------------------- #
def test_production_uses_the_k_and_threshold_that_were_tested():
    assert rates.PRIOR_K == 3.0 and rates.PRIOR_K in tested.K_GRID
    assert rates.MIN_PRIOR_MINUTES == tested.MIN_PRIOR_MINUTES
    assert rates.STATS == tested.STATS


# --- totals and the blend --------------------------------------------------------------------- #
def test_season_totals_sum_landed_gameweeks_by_code():
    elements = [{"id": 7, "code": 70}]
    live = _live({1: {7: {"minutes": 90, "expected_goals": "0.40", "bonus": 1}},
                  2: {7: {"minutes": 45, "expected_goals": "0.10", "bonus": 0}},
                  3: {99: {"minutes": 90}}})                       # not a current player: ignored
    got = rates.season_totals(elements, live)
    assert got[70]["minutes"] == 135 and got[70]["xg"] == pytest.approx(0.5) and got[70]["bonus"] == 1
    assert set(got) == {70}


def test_a_regular_last_season_blends_his_own_rate_with_this_season():
    players = [_player(1, 1800, xg=10.0)]                            # 0.5 per 90 last season
    got = rates.blended_rates(players, {1: {"minutes": 540, "xg": 6.0}})   # 1.0 per 90 now
    assert got[1]["xg"] == pytest.approx((6.0 + 3 * 0.5) / (6 + 3))
    assert got[1]["minutes"] == 540


def test_a_player_without_a_last_season_starts_from_his_positions_average():
    """The Nicolas Jackson case: six goals, under 270 minutes last season, projected zero."""
    players = [_player(1, 1800, xg=9.0), _player(2, 900, xg=6.0), _player(3, 100, xg=4.0)]
    got = rates.blended_rates(players, {})
    position_mean = 15.0 / 30.0                                      # regulars only: 15 xG in 30 nineties
    assert got[3]["xg"] == pytest.approx(position_mean)
    after = rates.blended_rates(players, {3: {"minutes": 720, "xg": 4.8}})
    assert after[3]["xg"] == pytest.approx((4.8 + 3 * position_mean) / (8 + 3))


# --- the xP builder ---------------------------------------------------------------------------- #
def _records(players, rate_map, recent_minutes=None):
    recs, _, coverage = compute_xp_records(
        players, {1: "A", 2: "B"}, [(1, 2)], _FakeEngine(), {"A": "A", "B": "B"},
        {p["code"]: 6.0 for p in players}, rates=rate_map, recent_minutes=recent_minutes)
    return {r["code"]: r for r in recs}, coverage


def test_a_striker_without_last_season_minutes_gets_his_share_once_rates_are_blended():
    """Both play every minute this season; only the newcomer is producing."""
    squad = [_player(c, 3000, starts=34) for c in (4, 5)]          # keeps club 1 above LOW_COVERAGE
    players = [_player(1, 3000, xg=12.0, starts=34), _player(2, 0, starts=0),
               _player(3, 3000, xg=1.0, team_id=2, starts=34), *squad]
    playing = {1: [90] * 6, 2: [90] * 6, 3: [90] * 6}
    old, _ = _records(players, None, playing)
    assert old[2]["breakdown"]["x_goals"] == 0.0
    live = {1: {"minutes": 540, "xg": 1.0}, 2: {"minutes": 540, "xg": 4.0}}
    new, _ = _records(players, rates.blended_rates(players, live), playing)
    assert new[2]["breakdown"]["x_goals"] > new[1]["breakdown"]["x_goals"] > 0


def test_this_seasons_minutes_count_towards_a_clubs_coverage():
    promoted = [_player(i, 0, team_id=1) for i in range(1, 12)] + [_player(20, 3000, team_id=2)]
    _, before = _records(promoted, rates.blended_rates(promoted, {}))
    assert before[1] < LOW_COVERAGE
    played = {i: {"minutes": 900.0} for i in range(1, 12)}          # ten games each
    _, after = _records(promoted, rates.blended_rates(promoted, played))
    assert after[1] >= LOW_COVERAGE


# --- the current player list ------------------------------------------------------------------ #
def _element(el, code, team, ownership="1.0", element_type=3):
    return {"id": el, "code": code, "team": team, "element_type": element_type,
            "web_name": f"p{el}", "selected_by_percent": ownership}


def test_club_and_ownership_come_from_today_not_from_july():
    history = {70: {"code": 70, "team_id": 4, "ownership": 1.9, "minutes": 2000, "starts": 22,
                    "xg": 3.0, "xa": 2.0, "dc": 10, "bonus": 5}}
    got = current_players([_element(7, 70, team=9, ownership="48.0")], history)[0]
    assert (got["team_id"], got["ownership"]) == (9, 48.0)
    assert (got["minutes"], got["xg"]) == (2000, 3.0)


def test_a_player_with_no_history_row_is_still_projected():
    got = current_players([_element(8, 80, team=1)], {})
    assert len(got) == 1 and got[0]["minutes"] == 0 and got[0]["position"] == "MID"


# --- freshness ---------------------------------------------------------------------------------- #
def test_a_finalised_gameweek_that_is_not_landed_is_reported():
    events = [{"id": g, "data_checked": g <= 9} for g in range(1, 12)]
    assert missing_gameweeks(events, landed={1, 2, 3, 4, 5, 6, 7, 9}, before_gw=11) == [8]
    # GW10 has finished but FPL has not finalised it yet: that is a normal day, not a gap
    assert missing_gameweeks(events, landed=set(range(1, 10)), before_gw=11) == []


def test_a_missing_gameweek_blocks_the_publish():
    meta = {"n_records": 600, "fallback_fixtures": 0,
            "source": {"failed": [], "unmapped_teams": [],
                       "player_data": {"through_gw": 9, "missing_gameweeks": [8]}}}
    assert any("not landed" in p for p in health_check(meta))
    meta["source"]["player_data"]["missing_gameweeks"] = []
    assert health_check(meta) == []
