"""Projected starting XI, derived from the minutes model.

Every other FPL tool scrapes a human's predicted lineup. This derives one: the eleven players
the minutes model expects to play most, in a legal shape. That makes it a *model output* rather
than an opinion — and therefore something we can score. Once the season starts, comparing the
projected XI against the actual XI gives an accuracy number no competitor publishes.

Availability is already baked in: `x_minutes` has been multiplied by the availability factor
upstream, so an injured player sits at 0 and falls out of contention without special-casing.

THE SHAPE comes from the club itself: the FPL-position split (defenders, midfielders, forwards)
it started with most often in its last five matches. It used to be whichever legal formation held
the most expected minutes, which favoured any position with many part-time players: Arsenal came
out 5-4-1 in Nov 2026 because five defenders each averaged over 55 minutes. Measured over GW6-10
of 2026-27, a club's usual shape was its next match's shape 66 times in 100. Some real shapes have
no FPL forward at all (4-6-0), which the fixed formation list could not express; that list is now
only the fallback for a club with no recent matches (preseason).

EACH PLAYER carries his starts in those matches. Over the same weeks, a player who had started
5 of the last 5 started the next match 91% of the time; 4 of 5, 64%; 2 or 3, 51%; 1, 29%; none, 4%.
The page turns that into a word, and says what the word means in those numbers.

Honest limits, stated rather than hidden:
  * It is a minutes ranking, not team news. It cannot know a manager's rotation plan, and in
    preseason it is ranking last season's minutes.
  * `confidence` is the mean expected-minutes share of the chosen XI — a rough "how nailed is
    this lineup", not a probability that the XI is exactly right.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence

# (defenders, midfielders, forwards) — every shape a side realistically lines up in, using
# FPL's own position classification (wing-backs count as DEF, wingers as MID).
FORMATIONS = (
    (3, 4, 3), (3, 5, 2),
    (4, 3, 3), (4, 4, 2), (4, 5, 1),
    (5, 2, 3), (5, 3, 2), (5, 4, 1),
)

MIN_MINUTES = 1.0  # below this a player is not a candidate at all (injured, or no history)
RECENT_MATCHES = 5
_POSITION = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def recent_starts(
    elements: Sequence[Mapping],
    live_by_gw: Mapping[int, Mapping],
    past_fixtures: Iterable[tuple[int, int, int]],
    last: int = RECENT_MATCHES,
) -> tuple[dict[int, tuple[int, int, int]], dict[int, tuple[int, int]]]:
    """Each club's usual shape and each player's starts, over the club's last `last` matches.

    Returns ({team_id: (defenders, midfielders, forwards)}, {element_id: (starts, matches)}).
    Only gameweeks in which the club played exactly once count: in a double gameweek FPL sums
    the two matches, and a blank has nothing to read. Club and position are today's, from the
    bootstrap, so a player who moved between Premier League clubs mid-window has his old club's
    starts counted (rare, and it can only overstate how settled he is by a match or two).
    """
    fixtures_in: Counter = Counter()
    for g, h, a in past_fixtures:
        fixtures_in[(g, h)] += 1
        fixtures_in[(g, a)] += 1
    team_of = {e["id"]: e.get("team") for e in elements}
    position = {e["id"]: _POSITION.get(e.get("element_type")) for e in elements}
    started = {
        g: {el["id"] for el in (live_by_gw[g].get("elements") or [])
            if int((el.get("stats") or {}).get("starts") or 0) >= 1}
        for g in live_by_gw
    }
    shapes: dict[int, tuple[int, int, int]] = {}
    starts: dict[int, tuple[int, int]] = {}
    for team in sorted({t for (_, t) in fixtures_in}):
        window = [g for g in sorted(started) if fixtures_in.get((g, team)) == 1][-last:]
        if not window:
            continue
        seen = []
        for g in window:
            n = Counter(position[e] for e in started[g] if team_of.get(e) == team)
            if n["GK"] == 1 and n["DEF"] + n["MID"] + n["FWD"] == 10:
                seen.append((n["DEF"], n["MID"], n["FWD"]))
        if seen:
            counts = Counter(seen)
            top = max(counts.values())
            # the most-used shape; a tie goes to whichever was used most recently
            shapes[team] = next(sh for sh in reversed(seen) if counts[sh] == top)
        for e, t in team_of.items():
            if t == team:
                starts[e] = (sum(1 for g in window if e in started[g]), len(window))
    return shapes, starts


def _row(r: dict, starts: Mapping[int, tuple[int, int]] | None = None) -> dict:
    """The per-player shape the serving layer exposes for a lineup slot."""
    avail = r.get("availability") or {}
    recent = (starts or {}).get(r["element_id"])
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
        # [started, of the club's last N matches]; None before the season has any
        "starts": list(recent) if recent else None,
    }


def projected_xi(
    records: Sequence[dict],
    team_id: int,
    shape: tuple[int, int, int] | None = None,
    starts: Mapping[int, tuple[int, int]] | None = None,
) -> dict | None:
    """The most-expected-minutes XI for a team in its usual shape, or None if one can't be fielded.

    `shape` is the club's usual (DEF, MID, FWD) split from `recent_starts`; without one, or when
    injuries leave too few players to fill it, the shape is whichever legal formation holds the
    most expected minutes. Returns {formation, basis, xi[], bench[], confidence}; `basis` says
    which ("recent" or "minutes"). `bench` is the next few by expected minutes — the players
    closest to displacing a starter, not a full FPL bench.
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
    basis = "minutes"
    if shape and all(len(by_pos[p]) >= n for p, n in zip(("DEF", "MID", "FWD"), shape, strict=True)):
        d, m, f = shape
        picked = by_pos["DEF"][:d] + by_pos["MID"][:m] + by_pos["FWD"][:f]
        best = (sum(p["x_minutes"] for p in picked), (d, m, f), picked)
        basis = "recent"
    for d, m, f in (() if best else FORMATIONS):
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
        "basis": basis,
        "xi": [_row(p, starts) for p in sorted(xi, key=lambda p: (
            {"GK": 0, "DEF": 1, "MID": 2, "FWD": 3}[p["position"]], -p["x_minutes"]))],
        "bench": [_row(p, starts) for p in bench],
        # mean share of a full match across the XI — a nailed-on side approaches 1.0
        "confidence": round(sum(p["x_minutes"] for p in xi) / (11 * 90.0), 3),
    }
