"""Flagship test: the point-in-time contract that keeps the backtest honest.

If this test ever regresses, the backtest is lying — future information is bleeding
into features. It is deliberately the most important test in the repo.
"""

import pytest

from fpledge.features import pointintime as pit

# Synthetic history for one team: three past matches and one FUTURE match,
# all with a `kickoff` epoch timestamp and a `goals` value.
ROWS = [
    {"kickoff": 100, "goals": 1},
    {"kickoff": 200, "goals": 3},
    {"kickoff": 300, "goals": 2},
    {"kickoff": 500, "goals": 9},  # FUTURE relative to as_of=400 — must be excluded
]
AS_OF = 400


def test_as_of_excludes_future_rows():
    past = pit.as_of_rows(ROWS, AS_OF)
    assert len(past) == 3
    assert all(r["kickoff"] < AS_OF for r in past)
    assert {r["goals"] for r in past} == {1, 3, 2}  # the 9 is not visible


def test_rolling_mean_ignores_future():
    # Mean of past goals = (1+3+2)/3 = 2.0. If leakage occurred, the 9 would pull
    # it to 3.75 — so this value is a direct leakage detector.
    assert pit.rolling_mean(ROWS, "goals", AS_OF) == pytest.approx(2.0)


def test_rolling_window_takes_most_recent():
    # Window of 2 most-recent past rows: goals 3 and 2 -> mean 2.5.
    assert pit.rolling_mean(ROWS, "goals", AS_OF, window=2) == pytest.approx(2.5)


def test_cold_start_returns_none_not_zero():
    assert pit.rolling_mean(ROWS, "goals", as_of=50) is None


def test_guard_raises_on_future_row():
    with pytest.raises(pit.LeakageError):
        pit.assert_point_in_time(ROWS, AS_OF)  # ROWS contains a future row
    # The leakage-safe view passes the guard.
    pit.assert_point_in_time(pit.as_of_rows(ROWS, AS_OF), AS_OF)
