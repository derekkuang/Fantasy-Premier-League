"""Per-90 player rates for the projection: last season blended with this season (HANDOFF §36).

    rate = (this season's total + PRIOR_K x prior) / (this season's 90s + PRIOR_K)

The prior is the player's own per-90 from last season if he played MIN_PRIOR_MINUTES there, and
otherwise the per-90 of last season's regulars at his position, so a new signing starts from a
plausible rate rather than zero. With PRIOR_K = 3 the prior counts as three full games: half the
weight after three games this season, a quarter after nine.

Measured, not chosen. Development seasons picked k = 3 from (3, 6, 10, 20), which barely
differed, and the blend then beat last-season-only rates on the held-out 2026-27 GW2-10 by
+0.022 Spearman. Weighting recent games more added nothing, twice, so this season's games count
equally. One difference from the test: there the position prior averaged every player of the
previous season; here it averages the current players' last seasons, which is what is on hand.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

STATS = ("xg", "xa", "dc", "bonus")
PRIOR_K = 3.0
MIN_PRIOR_MINUTES = 270

# event-live stat name for each rate
_LIVE_KEY = {"xg": "expected_goals", "xa": "expected_assists",
             "dc": "defensive_contribution", "bonus": "bonus"}


def season_totals(elements: Sequence[dict], live_by_gw: dict) -> dict:
    """{code: {"minutes", "xg", "xa", "dc", "bonus"}} summed over the landed gameweeks.

    The caller bounds `live_by_gw` to gameweeks before the one predicted. Blanks need no filter
    here, unlike recency minutes: a blank adds zero to every total, which leaves a rate unchanged.
    """
    code_of = {e["id"]: e["code"] for e in elements}
    out: dict = defaultdict(lambda: dict.fromkeys(("minutes", *STATS), 0.0))
    for payload in live_by_gw.values():
        for el in payload.get("elements", []):
            code = code_of.get(el.get("id"))
            if code is None:
                continue
            stats = el.get("stats") or {}
            out[code]["minutes"] += float(stats.get("minutes") or 0)
            for stat, key in _LIVE_KEY.items():
                out[code][stat] += float(stats.get(key) or 0)
    return dict(out)


def blended_rates(players: Sequence[dict], totals: dict, k: float = PRIOR_K) -> dict:
    """{code: {stat: per 90, ..., "minutes": this season's minutes}} for every player.

    `players` carry last season's totals (`minutes`, `xg`, `xa`, `dc`, `bonus`) and `position`.
    """
    sums: dict = defaultdict(lambda: dict.fromkeys(STATS, 0.0))
    nineties: dict = defaultdict(float)
    for p in players:
        if p["minutes"] >= MIN_PRIOR_MINUTES:
            for stat in STATS:
                sums[p["position"]][stat] += p[stat] or 0.0
            nineties[p["position"]] += p["minutes"] / 90.0
    position_mean = {pos: {s: sums[pos][s] / n for s in STATS} for pos, n in nineties.items()}

    out = {}
    for p in players:
        if p["minutes"] >= MIN_PRIOR_MINUTES:
            prior = {s: (p[s] or 0.0) / (p["minutes"] / 90.0) for s in STATS}
        else:
            prior = position_mean.get(p["position"], dict.fromkeys(STATS, 0.0))
        this = totals.get(p["code"], {})
        played = this.get("minutes", 0.0)
        out[p["code"]] = {
            **{s: (this.get(s, 0.0) + k * prior[s]) / (played / 90.0 + k) for s in STATS},
            "minutes": played,
        }
    return out
