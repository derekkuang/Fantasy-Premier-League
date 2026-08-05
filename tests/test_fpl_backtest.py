"""xP validation harness: it must run, and it must be point-in-time (no leakage).

The flagship check: corrupting a FUTURE gameweek's data must not change any earlier
gameweek's prediction. If it does, the walk-forward is leaking and every validation
number it produces is meaningless.
"""

import copy

import pytest

pytest.importorskip("numpy")
pytest.importorskip("scipy")

from fpledge.eval.fpl_backtest import validate_multi_gw, validate_xp  # noqa: E402


def _synthetic():
    teams = {"A": 1, "B": 2}
    kicks = ["2025-08-15", "2025-08-22", "2025-08-29", "2025-09-05", "2025-09-12", "2025-09-19"]
    fixtures = []
    for g in range(1, 7):
        home, away = ("1", "2") if g % 2 == 1 else ("2", "1")
        fixtures.append(
            {"gw": g, "home": home, "away": away, "home_goals": 2, "away_goals": 1,
             "kickoff": kicks[g - 1] + "T15:00:00Z"}
        )
    plan = [
        (101, "A", "MID"), (102, "A", "DEF"), (103, "A", "FWD"), (104, "A", "GK"),
        (201, "B", "MID"), (202, "B", "DEF"), (203, "B", "FWD"), (204, "B", "GK"),
    ]
    rows = []
    for g in range(1, 7):
        for el, team, pos in plan:
            tid = teams[team]
            opp = 2 if tid == 1 else 1
            was_home = (g % 2 == 1) == (tid == 1)
            rows.append(
                {"element": el, "name": f"p{el}", "position": pos, "team": team, "gw": g,
                 "opponent_team": opp, "was_home": was_home, "minutes": 90, "starts": 1,
                 "xg": 0.3 if pos == "FWD" else 0.05, "xa": 0.1,
                 "dc": 8 if pos in ("DEF", "MID") else 0, "bonus": 1,
                 "total_points": 5, "fpl_xp": 4.0}
            )
    return rows, fixtures, teams


def test_validate_runs_and_scores():
    rows, fixtures, teams = _synthetic()
    res = validate_xp(rows, fixtures, teams, burn_in=2, min_rate_minutes=90)
    assert res["n"] > 0
    assert res["all_players"]["mae_model"] >= 0.0


def test_validate_multi_gw_ranks_over_window():
    # 3 GWs, 12 players. Realized 3-GW sum is monotone in the player index; the model's
    # summed xP tracks it, FPL's summed xP inverts it. records: (gw, el, my, fpl, actual, pos, mins)
    recs = []
    for el in range(1, 13):
        for g in (1, 2, 3):
            recs.append((g, el, el * 0.9, float(13 - el), float(el), "MID", 90))
    r = validate_multi_gw(recs, window=3, min_players=5)
    assert r["window"] == 3 and r["windows_scored"] == 1 and r["n"] == 12
    assert r["gw_spearman_model"] > 0.9        # model ranks the 3-GW output well
    assert r["gw_spearman_fpl"] < -0.9         # FPL's inverted sum ranks it badly


def test_point_in_time_no_leakage():
    rows, fixtures, teams = _synthetic()
    _, base = validate_xp(rows, fixtures, teams, burn_in=2, min_rate_minutes=90, return_records=True)

    corrupt = copy.deepcopy(rows)
    for r in corrupt:               # blow up GW6's inputs
        if r["gw"] == 6:
            r["xg"], r["dc"], r["bonus"], r["minutes"] = 99.0, 99, 99, 0
    _, after = validate_xp(corrupt, fixtures, teams, burn_in=2, min_rate_minutes=90, return_records=True)

    # Every prediction for GW < 6 must be byte-identical — future data cannot leak backward.
    past_base = {(g, el): my for (g, el, my, *_ ) in base if g < 6}
    past_after = {(g, el): my for (g, el, my, *_ ) in after if g < 6}
    assert past_base == past_after
    assert past_base  # and there were actually earlier-GW predictions to compare


# --- the baseline must be a FORECAST, not a scraped post-match value ------------------ #
# Upstream's `xP` column is scraped after the gameweek and absorbs that gameweek's points
# through FPL's `form` average (see ingest.vaastav._add_clean_baseline). Scoring against it
# compares a projection to something that already saw the answer, which is how this project
# spent four months believing its model lost.

def test_the_shifted_baseline_is_preferred_over_the_scraped_one():
    """When both are present, the comparison must use the pre-deadline value."""
    from fpledge.eval.fpl_backtest import validate_xp

    rows, fixtures, teams = _synthetic()
    for r in rows:
        r["fpl_xp_prev"] = 0.0      # a deliberately useless forecast
        r["fpl_xp"] = float(r["total_points"])   # a perfect "forecast" — because it cheated
    out = validate_xp(rows, fixtures, teams, burn_in=2)
    assert out["baseline_clean"] is True
    # If the raw column were being used, its Spearman would be ~1.0 by construction.
    sp = out["played_only"]["gw_spearman_fpl"] if out.get("played_only") else None
    assert sp is None or sp < 0.99, "the scraped column leaked into the comparison"


def test_a_caller_without_the_shifted_column_is_flagged_not_silently_trusted():
    """Legacy callers still work — but the result says the baseline is not clean, so a
    number produced this way can never be mistaken for a valid comparison."""
    from fpledge.eval.fpl_backtest import validate_xp

    rows, fixtures, teams = _synthetic()
    for r in rows:
        r.pop("fpl_xp_prev", None)
    out = validate_xp(rows, fixtures, teams, burn_in=2)
    assert out["baseline_clean"] is False


def test_a_players_first_gameweek_has_no_baseline_and_is_skipped():
    """No prior forecast exists, so there is nothing to compare against. Scoring it would
    silently pit our projection against an implicit zero."""
    from fpledge.ingest.vaastav import _add_clean_baseline

    rows = [
        {"element": 7, "gw": 1, "fpl_xp": 3.0},
        {"element": 7, "gw": 2, "fpl_xp": 5.0},
        {"element": 7, "gw": 3, "fpl_xp": 4.0},
    ]
    _add_clean_baseline(rows)
    assert [r["fpl_xp_prev"] for r in rows] == [None, 3.0, 5.0]


def _match_saves(values):
    """One match per gameweek between the two synthetic teams. `values` is per-gameweek
    (home_keeper_saves, away_keeper_saves)."""
    out = []
    for g in range(1, 7):
        home, away = (1, 2) if g % 2 == 1 else (2, 1)
        h, a = values[g - 1]
        out.append({"gw": g, "home": home, "away": away,
                    "home_keeper_saves": h, "away_keeper_saves": a})
    return out


def test_saves_mode_shots_changes_only_goalkeepers():
    """The saves term is GK-only, so switching its model must leave every outfield
    projection untouched. A change there would mean the term had leaked into the wrong
    position and any measured 'improvement' would be unattributable."""
    rows, fixtures, teams = _synthetic()
    ms = _match_saves([(6, 1)] * 6)
    _, base = validate_xp(rows, fixtures, teams, burn_in=2, min_rate_minutes=90,
                          return_records=True)
    _, shot = validate_xp(rows, fixtures, teams, burn_in=2, min_rate_minutes=90,
                          saves_mode="shots", match_saves=ms, return_records=True)
    b = {(g, el): (my, pos) for (g, el, my, _f, _a, pos, _m) in base}
    s = {(g, el): (my, pos) for (g, el, my, _f, _a, pos, _m) in shot}
    outfield_changed = [k for k in b if b[k][1] != "GK" and b[k][0] != s[k][0]]
    gk_changed = [k for k in b if b[k][1] == "GK" and b[k][0] != s[k][0]]
    assert not outfield_changed
    assert gk_changed, "saves_mode='shots' changed nothing at all — the mode is not wired up"


def test_saves_rates_are_point_in_time():
    """The flagship check, for the saves feed specifically. Corrupting the LAST gameweek's
    save counts must not move any earlier prediction. Saves arrive per completed match, so
    it would be easy to fold a gameweek in before scoring it and never notice — the effect
    is a modest accuracy gain that looks exactly like the model working."""
    rows, fixtures, teams = _synthetic()
    clean = _match_saves([(4, 4)] * 6)
    dirty = _match_saves([(4, 4)] * 5 + [(500, 500)])   # absurd values, final GW only

    _, a = validate_xp(rows, fixtures, teams, burn_in=2, min_rate_minutes=90,
                       saves_mode="shots", match_saves=clean, return_records=True)
    _, b = validate_xp(rows, fixtures, teams, burn_in=2, min_rate_minutes=90,
                       saves_mode="shots", match_saves=dirty, return_records=True)
    past_a = {(g, el): my for (g, el, my, *_) in a if g < 6}
    past_b = {(g, el): my for (g, el, my, *_) in b if g < 6}
    assert past_a == past_b


def test_saves_mode_falls_back_when_no_data_is_supplied():
    """A dropped Understat fetch must degrade to the shipped behaviour, not to zero saves."""
    rows, fixtures, teams = _synthetic()
    _, base = validate_xp(rows, fixtures, teams, burn_in=2, min_rate_minutes=90,
                          return_records=True)
    _, none = validate_xp(rows, fixtures, teams, burn_in=2, min_rate_minutes=90,
                          saves_mode="shots", match_saves=None, return_records=True)
    assert {(g, el): my for (g, el, my, *_) in base} == {(g, el): my for (g, el, my, *_) in none}
