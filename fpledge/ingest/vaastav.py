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
_POS = {"GKP": "GK", "GK": "GK", "DEF": "DEF", "MID": "MID", "FWD": "FWD"}


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
    return rows


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
