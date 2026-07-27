"""xP validation harness: it must run, and it must be point-in-time (no leakage).

The flagship check: corrupting a FUTURE gameweek's data must not change any earlier
gameweek's prediction. If it does, the walk-forward is leaking and every validation
number it produces is meaningless.
"""

import copy

import pytest

pytest.importorskip("numpy")
pytest.importorskip("scipy")

from fpledge.eval.fpl_backtest import validate_xp  # noqa: E402


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
