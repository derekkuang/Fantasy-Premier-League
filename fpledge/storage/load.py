"""Load landed raw FPL JSON into the DuckDB tables.

Reads the newest immutable snapshot for each endpoint from `data/raw/` and loads
it idempotently (delete-then-insert per season, so a reload is safe and repeatable).

`player_key` uses FPL's `code` field, which is STABLE across seasons — unlike
`element_id`, which is reassigned each season. Getting this right now saves a
painful cross-season join later.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from .. import config
from . import duck


def _read_gz(fp: Path):
    with gzip.open(fp, "rt", encoding="utf-8") as f:
        return json.load(f)


def latest_raw(source: str, endpoint: str, season: str | None = None):
    """Return the parsed payload from the newest ingest_ts snapshot of an endpoint."""
    season = season or config.SEASON
    base = config.RAW_DIR / f"source={source}" / f"endpoint={endpoint}" / f"season={season}"
    snapshots = sorted(base.glob("ingest_ts=*/data.json.gz"))
    if not snapshots:
        raise FileNotFoundError(
            f"no landed data for source={source} endpoint={endpoint} season={season}. "
            f"Run scripts/pull_data.py first."
        )
    return _read_gz(snapshots[-1])  # lexicographic sort == chronological (UTC stamps)


def load_bootstrap(con, boot: dict, season: str | None = None) -> None:  # noqa: ANN001
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


def load_fixtures(con, fixtures: list, season: str | None = None) -> None:  # noqa: ANN001
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


def load_player_season(con, records: list[dict], season: str | None = None) -> int:  # noqa: ANN001
    """Idempotently load last-season per-player aggregates for goal/assist shares."""
    season = season or config.SEASON
    con.execute("DELETE FROM player_season WHERE season = ?", [season])
    rows = [
        (
            season, r["code"], r["element_id"], r["web_name"], r["team_id"], r["position"],
            r["minutes"], r["goals"], r["assists"], r["starts"], r["xg"], r["xa"],
        )
        for r in records
    ]
    con.executemany(
        "INSERT INTO player_season VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows
    )
    return len(rows)


def load_hist_matches(con, matches: list[dict]) -> int:  # noqa: ANN001
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


def load_all(season: str | None = None, con=None) -> dict:  # noqa: ANN001
    """Init schema, load latest bootstrap + fixtures, return row counts per table."""
    season = season or config.SEASON
    owns = con is None
    con = con or duck.connect()
    try:
        duck.init_schema(con)
        load_bootstrap(con, latest_raw("fpl_api", "bootstrap", season), season)
        load_fixtures(con, latest_raw("fpl_api", "fixtures", season), season)
        return {
            t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            for t in ("teams", "players", "fixtures")
        }
    finally:
        if owns:
            con.close()
