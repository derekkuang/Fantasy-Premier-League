"""Projected starting XI, derived from the minutes model.

Every other FPL tool scrapes a human's predicted lineup. This derives one: the eleven players
the minutes model expects to play most, in a legal shape. That makes it a *model output* rather
than an opinion — and therefore something we can score. Once the season starts, comparing the
projected XI against the actual XI gives an accuracy number no competitor publishes.

Availability is already baked in: `x_minutes` has been multiplied by the availability factor
upstream, so an injured player sits at 0 and falls out of contention without special-casing.

Honest limits, stated rather than hidden:
  * It is a minutes ranking, not team news. It cannot know a manager's rotation plan, and in
    preseason it is ranking last season's minutes.
  * `confidence` is the mean expected-minutes share of the chosen XI — a rough "how nailed is
    this lineup", not a probability that the XI is exactly right.
"""

from __future__ import annotations

from collections.abc import Sequence

# (defenders, midfielders, forwards) — every shape a side realistically lines up in, using
# FPL's own position classification (wing-backs count as DEF, wingers as MID).
FORMATIONS = (
    (3, 4, 3), (3, 5, 2),
    (4, 3, 3), (4, 4, 2), (4, 5, 1),
    (5, 2, 3), (5, 3, 2), (5, 4, 1),
)

MIN_MINUTES = 1.0  # below this a player is not a candidate at all (injured, or no history)


def _row(r: dict) -> dict:
    """The per-player shape the serving layer exposes for a lineup slot."""
    avail = r.get("availability") or {}
    return {
        "element_id": r["element_id"],
        "web_name": r["web_name"],
        "position": r["position"],
        "x_minutes": round(r["x_minutes"], 1),
        "xp": round(r.get("xp", 0.0), 2),
        "price": r.get("price"),
        "status": avail.get("status"),
        "chance": avail.get("chance"),
        "penalties": (r.get("set_pieces") or {}).get("penalties"),
    }


def projected_xi(records: Sequence[dict], team_id: int) -> dict | None:
    """The most-expected-minutes legal XI for a team, or None if one can't be fielded.

    Returns {formation, xi[], bench[], confidence}. `bench` is the next few by expected
    minutes — the players closest to displacing a starter, not a full FPL bench.
    """
    squad = [r for r in records if r.get("team_id") == team_id and r.get("x_minutes", 0) >= MIN_MINUTES]
    by_pos: dict[str, list[dict]] = {"GK": [], "DEF": [], "MID": [], "FWD": []}
    for r in squad:
        if r["position"] in by_pos:
            by_pos[r["position"]].append(r)
    for players in by_pos.values():
        players.sort(key=lambda r: r["x_minutes"], reverse=True)

    if not by_pos["GK"]:
        return None

    best = None
    for d, m, f in FORMATIONS:
        if len(by_pos["DEF"]) < d or len(by_pos["MID"]) < m or len(by_pos["FWD"]) < f:
            continue
        picked = by_pos["DEF"][:d] + by_pos["MID"][:m] + by_pos["FWD"][:f]
        total = sum(p["x_minutes"] for p in picked)
        if best is None or total > best[0]:
            best = (total, (d, m, f), picked)

    if best is None:
        return None

    total, (d, m, f), outfield = best
    keeper = by_pos["GK"][0]
    xi = [keeper] + outfield
    chosen = {p["element_id"] for p in xi}

    # nearest misses — whoever the model has closest to a start without being in the XI
    bench = sorted(
        (r for r in squad if r["element_id"] not in chosen),
        key=lambda r: r["x_minutes"], reverse=True,
    )[:4]

    return {
        "formation": f"{d}-{m}-{f}",
        "xi": [_row(p) for p in sorted(xi, key=lambda p: (
            {"GK": 0, "DEF": 1, "MID": 2, "FWD": 3}[p["position"]], -p["x_minutes"]))],
        "bench": [_row(p) for p in bench],
        # mean share of a full match across the XI — a nailed-on side approaches 1.0
        "confidence": round(sum(p["x_minutes"] for p in xi) / (11 * 90.0), 3),
    }
