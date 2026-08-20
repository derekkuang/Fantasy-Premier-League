"""Load landed raw FPL JSON into the DuckDB tables.

Reads the newest immutable snapshot for each endpoint from `data/raw/` and loads
it idempotently (delete-then-insert per season, so a reload is safe and repeatable).

`player_key` uses FPL's `code` field, which is STABLE across seasons — unlike
`element_id`, which is reassigned each season. Getting this right now saves a
painful cross-season join later.
"""

from __future__ import annotations

from .. import config
from ..ingest import landing
from . import duck


def latest_raw(source: str, endpoint: str, season: str | None = None):
    """Return the parsed payload from the newest ingest_ts snapshot of an endpoint.

    Listing goes through `landing` so this works against either backend — a glob over
    `config.RAW_DIR` would find nothing once the raw zone lives in S3.
    """
    season = season or config.SEASON
    snapshots = landing.list_partitions(source, endpoint, season)
    if not snapshots:
        raise FileNotFoundError(
            f"no landed data for source={source} endpoint={endpoint} season={season}. "
            f"Run scripts/pull_data.py first."
        )
    return landing.read_json(snapshots[-1])  # lexicographic == chronological (UTC stamps)


def load_bootstrap(con, boot: dict, season: str | None = None) -> None:
    season = season or config.SEASON

    teams = [(season, t["id"], t["name"]) for t in boot["teams"]]
    con.execute("DELETE FROM teams WHERE season = ?", [season])
    con.executemany("INSERT INTO teams VALUES (?, ?, ?)", teams)

    players = [
        (
            season,
            e["id"],
            str(e["code"]),  # stable cross-season key
            e["web_name"],
            config.ELEMENT_TYPE_TO_POS[e["element_type"]],
            e["team"],
        )
        for e in boot["elements"]
    ]
    con.execute("DELETE FROM players WHERE season = ?", [season])
    con.executemany("INSERT INTO players VALUES (?, ?, ?, ?, ?, ?)", players)


def load_fixtures(con, fixtures: list, season: str | None = None) -> None:
    season = season or config.SEASON

    def _ts(v):
        # FPL kickoff_time is ISO-8601 with a trailing 'Z'; DuckDB's TIMESTAMP
        # parses the naive form, so drop the 'Z' (times are already UTC).
        return v[:-1] if isinstance(v, str) and v.endswith("Z") else v

    rows = [
        (
            fx["id"],
            season,
            fx.get("event"),
            fx["team_h"],
            fx["team_a"],
            _ts(fx.get("kickoff_time")),
            bool(fx.get("finished", False)),
            fx.get("team_h_score"),
            fx.get("team_a_score"),
        )
        for fx in fixtures
    ]
    con.execute("DELETE FROM fixtures WHERE season = ?", [season])
    con.executemany(
        "INSERT INTO fixtures VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows
    )


def load_player_season(con, records: list[dict], season: str | None = None) -> int:
    """Idempotently load last-season per-player aggregates for goal/assist shares."""
    season = season or config.SEASON
    con.execute("DELETE FROM player_season WHERE season = ?", [season])
    rows = [
        (
            season, r["code"], r["element_id"], r["web_name"], r["team_id"], r["position"],
            r["minutes"], r["goals"], r["assists"], r["starts"], r["xg"], r["xa"],
            r["ownership"], r["ep_next"], r["dc"], r["bonus"],
        )
        for r in records
    ]
    con.executemany(
        "INSERT INTO player_season VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows
    )
    return len(rows)


def load_hist_matches(con, matches: list[dict]) -> int:
    """Idempotently load historical results + closing odds into hist_matches."""
    con.execute("DELETE FROM hist_matches")
    rows = [
        (
            m["season"], m["date"], m["home"], m["away"],
            m["home_goals"], m["away_goals"],
            m["close_h"], m["close_d"], m["close_a"],
        )
        for m in matches
    ]
    con.executemany("INSERT INTO hist_matches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    return len(rows)


def load_all(season: str | None = None, con=None) -> dict:
    """Init schema, rebuild every table from the landed raw zone, return row counts.

    DuckDB here is DERIVED state — anything in it must be rebuildable from landed raw alone,
    because a scheduler's runner starts with no database at all. This function is that rebuild.

    `player_season` comes from the landed `player_history` object rather than 558 fresh FPL API
    calls, and the distinction matters twice over: past-season aggregates are static for the
    entire season, so re-pulling them daily would be pointless load on FPL's API; and the first
    cloud precompute failed exactly here — the laptop's DuckDB had the table (pull_player_history
    had loaded it as a side effect months ago) and the runner's did not, because no code path
    rebuilt it from the landed object. Missing is tolerated with a loud count of 0 rather than an
    exception: the artifact for a brand-new season legitimately precedes any history pull.
    """
    season = season or config.SEASON
    owns = con is None
    con = con or duck.connect()
    try:
        duck.init_schema(con)
        load_bootstrap(con, latest_raw("fpl_api", "bootstrap", season), season)
        load_fixtures(con, latest_raw("fpl_api", "fixtures", season), season)
        try:
            history = latest_raw("fpl_api", "player_history", season)
        except FileNotFoundError:
            history = None
        if history is not None:
            load_player_season(con, history, season)
        return {
            t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            for t in ("teams", "players", "fixtures", "player_season")
        }
    finally:
        if owns:
            con.close()
