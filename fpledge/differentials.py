"""Differential finder — high-xP, low-owned players for climbing overall rank.

A differential only helps your rank if it's genuinely good, so this ranks by differential
value (xP x (1 - effective ownership)) subject to an xP floor — never surfacing an unowned
dud (the same discipline as the differential captain).
"""

from __future__ import annotations

from collections.abc import Sequence


def find_differentials(
    records: Sequence[dict],
    max_ownership: float = 15.0,
    min_xp: float = 3.5,
    position: str | None = None,
    top: int = 15,
) -> list[dict]:
    """Best low-owned picks from xP records, ranked by differential value.

    Excludes low-data (promoted) teams; requires ownership <= max_ownership and xp >= min_xp.
    """
    candidates = [
        r for r in records
        if not r["low_cov"]
        and r["ownership"] <= max_ownership
        and r["xp"] >= min_xp
        and (position is None or r["position"] == position)
    ]
    candidates.sort(key=lambda r: r["diff_value"], reverse=True)
    return candidates[:top]
