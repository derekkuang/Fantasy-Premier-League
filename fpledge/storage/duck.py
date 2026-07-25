"""DuckDB connection + schema.

DuckDB is the single analytics engine (its native ASOF JOIN is exactly what
point-in-time feature building wants). `duckdb` is a declared dependency, imported
lazily so the stdlib-only core stays importable without it.
"""

from __future__ import annotations

from .. import config

# Fact / dimension / prediction tables. Prediction tables carry model_version +
# run_ts so a prediction is never silently overwritten and can always be scored
# against what was actually known at the time it was made.
SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS teams (
    season      VARCHAR,
    team_id     INTEGER,
    name        VARCHAR,
    PRIMARY KEY (season, team_id)
);

CREATE TABLE IF NOT EXISTS players (
    season       VARCHAR,
    element_id   INTEGER,
    player_key   VARCHAR,   -- stable across seasons (element_id is NOT)
    name         VARCHAR,
    position     VARCHAR,
    team_id      INTEGER,
    PRIMARY KEY (season, element_id)
);

CREATE TABLE IF NOT EXISTS fixtures (
    fixture_id   INTEGER PRIMARY KEY,
    season       VARCHAR,
    gw           INTEGER,
    home_id      INTEGER,
    away_id      INTEGER,
    kickoff_utc  TIMESTAMP,
    finished     BOOLEAN,
    home_goals   INTEGER,
    away_goals   INTEGER
);

CREATE TABLE IF NOT EXISTS player_gw (
    season       VARCHAR,
    element_id   INTEGER,
    gw           INTEGER,
    fixture_id   INTEGER,
    kickoff_utc  TIMESTAMP,       -- as-of key for point-in-time features
    minutes      INTEGER,
    goals        INTEGER,
    assists      INTEGER,
    goals_conceded INTEGER,
    saves        INTEGER,
    cbit         INTEGER,         -- clearances+blocks+interceptions+tackles
    recoveries   INTEGER,
    bps          INTEGER,
    xg           DOUBLE,
    xa           DOUBLE,
    total_points INTEGER,
    PRIMARY KEY (season, element_id, gw)
);

CREATE TABLE IF NOT EXISTS team_match (
    fixture_id   INTEGER,
    team_id      INTEGER,
    xg_for       DOUBLE,
    xg_against   DOUBLE,
    PRIMARY KEY (fixture_id, team_id)
);

CREATE TABLE IF NOT EXISTS odds (
    fixture_id   INTEGER,
    bookie       VARCHAR,
    market       VARCHAR,
    selection    VARCHAR,
    decimal_odds DOUBLE,
    captured_ts  TIMESTAMP
);

-- last-season per-player aggregates (FPL history_past) for goal/assist shares
CREATE TABLE IF NOT EXISTS player_season (
    season     VARCHAR,     -- the CURRENT season this prior-season row informs
    code       INTEGER,     -- stable FPL player code
    element_id INTEGER,
    web_name   VARCHAR,
    team_id    INTEGER,     -- current team
    position   VARCHAR,
    minutes    INTEGER,
    goals      INTEGER,
    assists    INTEGER,
    starts     INTEGER,
    xg         DOUBLE,      -- last season expected goals
    xa         DOUBLE,      -- last season expected assists
    PRIMARY KEY (season, code)
);

-- historical results + closing 1X2 odds (Football-Data.co.uk) for fitting/backtest
CREATE TABLE IF NOT EXISTS hist_matches (
    season       VARCHAR,
    date         DATE,
    home         VARCHAR,
    away         VARCHAR,
    home_goals   INTEGER,
    away_goals   INTEGER,
    close_h      DOUBLE,
    close_d      DOUBLE,
    close_a      DOUBLE
);

-- write-once predictions ---------------------------------------------------
CREATE TABLE IF NOT EXISTS match_pred (
    fixture_id   INTEGER,
    model_ver    VARCHAR,
    run_ts       TIMESTAMP,
    lambda_h     DOUBLE,
    lambda_a     DOUBLE,
    p_home       DOUBLE,
    p_draw       DOUBLE,
    p_away       DOUBLE,
    p_btts       DOUBLE,
    p_over25     DOUBLE,
    p_cs_home    DOUBLE,
    p_cs_away    DOUBLE
);

CREATE TABLE IF NOT EXISTS player_xp (
    season       VARCHAR,
    element_id   INTEGER,
    gw           INTEGER,
    model_ver    VARCHAR,
    run_ts       TIMESTAMP,
    x_mins       DOUBLE,
    p_start      DOUBLE,
    x_goals      DOUBLE,
    x_assists    DOUBLE,
    p_cs         DOUBLE,
    x_dc_points  DOUBLE,
    xp           DOUBLE
);
"""


def connect(read_only: bool = False):  # noqa: ANN201
    """Open (and lazily create) the project DuckDB database."""
    import duckdb  # noqa: PLC0415

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(config.DUCKDB_PATH), read_only=read_only)


def init_schema(con=None) -> None:  # noqa: ANN001
    """Create all tables if they do not exist."""
    owns = con is None
    con = con or connect()
    try:
        con.execute(SCHEMA_DDL)
    finally:
        if owns:
            con.close()
