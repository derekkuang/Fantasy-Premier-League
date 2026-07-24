"""Point-in-time (as-of) primitives — the anti-leakage backbone (stdlib-only).

Contract: to compute any feature for a fixture that kicks off at time T, you may
only use rows whose own timestamp is STRICTLY BEFORE T. Every feature builder
routes through `as_of_rows` / `assert_point_in_time` so this is enforced, not
hoped for. The flagship test (`tests/test_no_leakage.py`) exercises exactly this.
"""

from __future__ import annotations

from collections.abc import Sequence


class LeakageError(AssertionError):
    """Raised when a feature computation would consume future information."""


def as_of_rows(
    rows: Sequence[dict], as_of, ts_key: str = "kickoff"
) -> list[dict]:
    """Return only rows strictly before `as_of` — the leakage-safe view.

    `as_of` and each `row[ts_key]` must be mutually comparable (e.g. both ISO-8601
    strings, both epoch numbers, or both datetimes).
    """
    return [r for r in rows if r[ts_key] < as_of]


def assert_point_in_time(rows: Sequence[dict], as_of, ts_key: str = "kickoff") -> None:
    """Guard: raise LeakageError if any row is at or after `as_of`."""
    for r in rows:
        if r[ts_key] >= as_of:
            raise LeakageError(
                f"row at {r[ts_key]!r} is not strictly before as_of={as_of!r} "
                f"(key={ts_key!r}) — this would leak future information"
            )


def rolling_mean(
    rows: Sequence[dict],
    value_key: str,
    as_of,
    window: int | None = None,
    ts_key: str = "kickoff",
) -> float | None:
    """Mean of `value_key` over the most-recent `window` rows before `as_of`.

    Returns None when there is no history yet (a real cold-start signal the model
    should see, not a silently-imputed zero).
    """
    past = as_of_rows(rows, as_of, ts_key)
    past.sort(key=lambda r: r[ts_key])
    if window is not None:
        past = past[-window:]
    if not past:
        return None
    return sum(r[value_key] for r in past) / len(past)
