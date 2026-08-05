"""Ingest vaastav/Fantasy-Premier-League historical per-gameweek data.

This is the ground truth for validating the xP model: `merged_gw.csv` gives per-player,
per-gameweek REALIZED stats + `total_points` (what actually happened) + `xP` (FPL's own
expected-points, the benchmark to beat). `fixtures.csv` + `teams.csv` supply results and
the id<->name map so the match engine can be refit point-in-time.
"""

from __future__ import annotations

import csv
import io

from . import landing

VAASTAV_BASE = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data"
# FPL itself has exactly four positions (element_type 1-4). This dataset carries a few extra
# labels across seasons — "GKP" for goalkeepers, and in 2024-25 an "AM" on ~1.2% of rows, which
# is not an FPL position at all. Everything is normalised to the four the scoring rules know,
# with AM folded into MID because that is how the game scores an attacking midfielder. Left
# unmapped it reached `config.GOAL_POINTS[pos]` and raised KeyError mid-walk-forward.
_POS = {
    "GKP": "GK", "GK": "GK", "DEF": "DEF", "MID": "MID", "FWD": "FWD",
    "AM": "MID",
}


def _get(url: str) -> str:
    import requests  # noqa: PLC0415

    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    return resp.text


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _i(v) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def fetch_player_gws(season: str) -> list[dict]:
    """One record per player per gameweek (realized stats + total_points + FPL xP)."""
    text = _get(f"{VAASTAV_BASE}/{season}/gws/merged_gw.csv")
    landing.land(text, source="vaastav", endpoint="merged_gw", season=season)
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        rows.append(
            {
                "element": _i(r.get("element")),
                "name": r.get("name"),
                "position": _POS.get((r.get("position") or "").upper(), r.get("position")),
                "team": r.get("team"),
                "gw": _i(r.get("GW") or r.get("round")),
                "opponent_team": _i(r.get("opponent_team")),
                "was_home": (r.get("was_home", "").strip().lower() == "true"),
                "minutes": _i(r.get("minutes")),
                "starts": _i(r.get("starts")),
                "xg": _f(r.get("expected_goals")),
                "xa": _f(r.get("expected_assists")),
                "dc": _i(r.get("defensive_contribution")),
                "bonus": _i(r.get("bonus")),
                "total_points": _i(r.get("total_points")),
                "fpl_xp": _f(r.get("xP")),
            }
        )
    _add_clean_baseline(rows)
    return rows


def _add_clean_baseline(rows: list[dict]) -> None:
    """Add `fpl_xp_prev` — FPL's projection as it stood BEFORE each gameweek.

    THE COLUMN AS SHIPPED IS NOT A PRE-MATCH FORECAST. Upstream's README says so plainly:
    `xP` is the bootstrap `ep_this` field, "the scraper runs AFTER each gameweek ends, so if
    FPL updates `ep_this` post-match, the scraped value will contain information that was not
    available to managers before the deadline", and "using it unshifted as a feature to predict
    same-GW `total_points` has been observed to cause severe lookahead bias". The recommended
    fix is exactly this: "apply `shift(1)` within each `element` group, or exclude the column".

    The mechanism is visible in the same README: live `ep_this` correlates ~0.98 with `form`,
    and `form` is a rolling points average that absorbs a gameweek's points once it finishes.
    So a value scraped after GW N encodes GW N's points — not through match detail, which is
    why it shows no correlation at all with conversion luck (-0.018) or cards (-0.033), but
    through the points total itself entering the average it is computed from.

    Measured on 2024-25, played-only per-GW Spearman against realised points:
        as-scraped  0.568   <- not a forecast; it has already seen the gameweek
        shifted     0.292   <- the same number, using only what preceded the deadline

    Both are kept. `fpl_xp` remains available so the contamination can be demonstrated rather
    than asserted; `fpl_xp_prev` is what any honest comparison must use.
    """
    by_el: dict = {}
    for r in rows:
        by_el.setdefault(r["element"], []).append(r)
    for series in by_el.values():
        series.sort(key=lambda r: r["gw"])
        prev = None
        for r in series:
            r["fpl_xp_prev"] = prev
            prev = r["fpl_xp"]


def fetch_fixtures(season: str) -> list[dict]:
    """Match results (team ids) with gameweek + kickoff, for point-in-time engine fits."""
    text = _get(f"{VAASTAV_BASE}/{season}/fixtures.csv")
    landing.land(text, source="vaastav", endpoint="fixtures", season=season)
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        if r.get("finished", "").strip().lower() != "true":
            continue
        out.append(
            {
                "gw": _i(r.get("event")),
                "home": str(_i(r.get("team_h"))),
                "away": str(_i(r.get("team_a"))),
                "home_goals": _i(r.get("team_h_score")),
                "away_goals": _i(r.get("team_a_score")),
                "kickoff": r.get("kickoff_time"),
            }
        )
    return out


def fetch_teams(season: str) -> dict:
    """Return {name -> team_id} for the season."""
    text = _get(f"{VAASTAV_BASE}/{season}/teams.csv")
    landing.land(text, source="vaastav", endpoint="teams", season=season)
    return {r["name"]: _i(r["id"]) for r in csv.DictReader(io.StringIO(text))}
