"""Deadline selection for the pre-deadline snapshot.

The one thing this script must never get wrong is WHICH deadline it is capturing for. A
snapshot filed against the wrong gameweek is worse than no snapshot: it looks like evidence
and is not, which is exactly the failure this whole collection effort exists to fix
(docs/HANDOFF.md §16).
"""

from __future__ import annotations

import importlib.util
import pathlib
from datetime import UTC, datetime

_spec = importlib.util.spec_from_file_location(
    "snapshot", pathlib.Path(__file__).resolve().parent.parent / "scripts" / "snapshot.py"
)
snapshot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(snapshot)   # type: ignore[union-attr]


def _events():
    return [
        {"id": 1, "deadline_time": "2026-08-21T17:30:00Z"},
        {"id": 2, "deadline_time": "2026-08-28T17:30:00Z"},
        {"id": 3, "deadline_time": "2026-09-04T17:30:00Z"},
    ]


def test_picks_the_next_deadline_not_the_first():
    """Mid-season the earliest deadline is in the past; capturing for GW1 in October would
    file a snapshot against a gameweek that has already been played."""
    now = datetime(2026, 8, 25, tzinfo=UTC)
    gw, deadline = snapshot.next_deadline(_events(), now)
    assert gw == 2
    assert deadline.day == 28


def test_a_deadline_that_has_just_passed_is_not_selected():
    """One second after a deadline the gameweek is locked — anything captured now is
    post-deadline and must not be filed as pre."""
    now = datetime(2026, 8, 21, 17, 30, 1, tzinfo=UTC)
    gw, _ = snapshot.next_deadline(_events(), now)
    assert gw == 2


def test_season_over_returns_nothing_rather_than_guessing():
    gw, deadline = snapshot.next_deadline(_events(), datetime(2027, 6, 1, tzinfo=UTC))
    assert gw is None and deadline is None


def test_events_without_a_deadline_are_ignored():
    """FPL publishes placeholder events with null deadlines; a crash here would silently
    end the weekly capture."""
    events = [{"id": 9, "deadline_time": None}, {"id": 10, "deadline_time": ""}, *_events()]
    gw, _ = snapshot.next_deadline(events, datetime(2026, 8, 1, tzinfo=UTC))
    assert gw == 1
