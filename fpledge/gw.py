"""Assemble xP records for a gameweek end-to-end: load -> fit engine -> compute records.

The single convenience entry point shared by the xP table and the squad optimiser, so both
scripts stay thin and can't drift apart.
"""

from __future__ import annotations

from . import config
from .ingest import footballdata
from .models.dixon_coles import DixonColesModel
from .models.teammap import build_team_map
from .models.xp_table import compute_xp_records
from .storage import duck
from .storage import load as storeload

SEASONS = ["2324", "2425", "2526"]
PLAYER_COLS = [
    "code", "element_id", "team_id", "position", "web_name", "minutes", "starts",
    "xg", "xa", "dc", "bonus", "ownership",
]


def records_for_gw(gw: int, seasons: list[str] | None = None) -> dict | None:
    """Return {records, skipped, coverage, fpl_teams} for a gameweek, or None if no player data."""
    con = duck.connect()
    duck.init_schema(con)
    players = [
        dict(zip(PLAYER_COLS, r, strict=True))
        for r in con.execute(
            f"SELECT {', '.join(PLAYER_COLS)} FROM player_season WHERE season = ?",
            [config.SEASON],
        ).fetchall()
    ]
    fpl_teams = {
        tid: name
        for tid, name in con.execute(
            "SELECT team_id, name FROM teams WHERE season = ?", [config.SEASON]
        ).fetchall()
    }
    fixtures = con.execute(
        "SELECT home_id, away_id FROM fixtures WHERE season = ? AND gw = ?",
        [config.SEASON, gw],
    ).fetchall()
    con.close()
    if not players:
        return None

    boot = storeload.latest_raw("fpl_api", "bootstrap")
    prices = {e["code"]: e["now_cost"] / 10.0 for e in boot["elements"]}
    # live availability: (chance_of_playing_next_round, status) per player, to discount
    # injured/doubtful players in the current-GW prediction (the production half of fix #2).
    availability = {
        e["code"]: (e.get("chance_of_playing_next_round"), e.get("status"))
        for e in boot["elements"]
    }

    matches = footballdata.load_seasons(seasons or SEASONS)
    engine = DixonColesModel(half_life_days=180).fit(matches)
    fd_names = sorted({m["home"] for m in matches} | {m["away"] for m in matches})
    tmap = build_team_map(list(fpl_teams.values()), fd_names)

    records, fallback, coverage = compute_xp_records(
        players, fpl_teams, fixtures, engine, tmap, prices, availability=availability
    )
    return {"records": records, "fallback": fallback, "coverage": coverage, "fpl_teams": fpl_teams}
