"""Assemble xP records for a gameweek end-to-end: load -> fit engine -> compute records.

The single convenience entry point shared by the xP table and the squad optimiser, so both
scripts stay thin and can't drift apart.
"""

from __future__ import annotations

from collections import defaultdict

from . import config
from .fdr import fixture_ticker
from .ingest import footballdata
from .models.dixon_coles import DixonColesModel
from .models.teammap import build_team_map
from .models.xp_table import compute_multi_gw_xp, compute_xp_records
from .storage import duck
from .storage import load as storeload

SEASONS = ["2324", "2425", "2526"]
PLAYER_COLS = [
    "code", "element_id", "team_id", "position", "web_name", "minutes", "starts",
    "xg", "xa", "dc", "bonus", "ownership",
]


def _load_inputs(gw: int, horizon: int, seasons: list[str] | None) -> dict | None:
    """Shared load + engine fit for a gameweek window [gw, gw+horizon).

    Returns everything the xP records and the fixture ticker both need (players, teams,
    fixtures, prices, availability, fitted engine, team map), or None if there is no
    player data for the season. Single expensive step (the Dixon-Coles fit) done once.
    """
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
        "SELECT gw, home_id, away_id FROM fixtures WHERE season = ? AND gw >= ? AND gw < ?",
        [config.SEASON, gw, gw + horizon],
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

    return {
        "players": players, "fpl_teams": fpl_teams, "fixtures": fixtures,
        "prices": prices, "availability": availability, "engine": engine, "tmap": tmap,
    }


def records_for_gw(gw: int, seasons: list[str] | None = None) -> dict | None:
    """Return {records, fallback, coverage, fpl_teams} for a gameweek, or None if no player data."""
    inp = _load_inputs(gw, horizon=1, seasons=seasons)
    if inp is None:
        return None
    gw_fixtures = [(h, a) for (g, h, a) in inp["fixtures"] if g == gw]
    records, fallback, coverage = compute_xp_records(
        inp["players"], inp["fpl_teams"], gw_fixtures, inp["engine"], inp["tmap"],
        inp["prices"], availability=inp["availability"],
    )
    return {
        "records": records, "fallback": fallback, "coverage": coverage,
        "fpl_teams": inp["fpl_teams"],
    }


def assemble_for_serving(
    gw: int, horizon: int = 8, seasons: list[str] | None = None
) -> dict | None:
    """Everything the API precompute needs from one engine fit: the GW xP records AND the
    true-FDR fixture ticker for [gw, gw+horizon). Returns None if there is no player data.

    The fixture ticker cannot be derived from records alone (it needs the fitted engine +
    team map + multi-GW fixtures), so it is produced here where those live, then serialised.
    """
    inp = _load_inputs(gw, horizon=horizon, seasons=seasons)
    if inp is None:
        return None
    gw_fixtures = [(h, a) for (g, h, a) in inp["fixtures"] if g == gw]
    records, fallback, coverage = compute_xp_records(
        inp["players"], inp["fpl_teams"], gw_fixtures, inp["engine"], inp["tmap"],
        inp["prices"], availability=inp["availability"],
    )
    ticker_fixtures = [{"gw": g, "home_id": h, "away_id": a} for (g, h, a) in inp["fixtures"]]
    ticker = fixture_ticker(
        inp["engine"], ticker_fixtures, inp["fpl_teams"], inp["tmap"],
        start_gw=gw, horizon=horizon,
    )

    # Per-player xP for each upcoming GW (same engine/shares, different opponent), so the
    # predictions can rank on a multi-week outlook, not just the current gameweek.
    fixtures_by_gw: dict = defaultdict(list)
    for g, h, a in inp["fixtures"]:
        fixtures_by_gw[g].append((h, a))
    multi = compute_multi_gw_xp(
        inp["players"], inp["fpl_teams"], fixtures_by_gw, inp["engine"], inp["tmap"],
        inp["prices"], ticker, sorted(fixtures_by_gw), availability=inp["availability"],
    )
    for r in records:
        fx = multi.get(r["element_id"], [])
        r["fixtures"] = fx                                     # next GWs: {gw, opp, home, xp, fdr}
        r["xp_next3"] = round(sum(c["xp"] for c in fx[:3]), 2)  # 3-week outlook (incl. this GW)

    return {
        "records": records, "fallback": fallback, "coverage": coverage,
        "fpl_teams": inp["fpl_teams"], "fixture_ticker": ticker, "horizon": horizon,
    }
