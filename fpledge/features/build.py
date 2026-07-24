"""DuckDB feature builder — point-in-time correct by construction.

Every feature for a fixture kicking off at T is computed only from rows with
kickoff_utc < T. DuckDB's ASOF JOIN expresses exactly this; the same contract is
unit-tested in its pure-Python form in `pointintime` and `tests/test_no_leakage`.

`duckdb`/`pandas` are declared deps, imported lazily. This is the Phase-1 skeleton:
the SQL shape is real; extend the SELECT list as you add features.
"""

from __future__ import annotations

from .. import config
from ..storage import duck

# Team rolling-form features as-of each fixture's kickoff. ASOF JOIN grabs, for
# each fixture, the correct point-in-time aggregate without any future rows.
TEAM_FORM_SQL = """
WITH team_gw AS (
    SELECT team_id, kickoff_utc, xg_for, xg_against
    FROM team_match tm
    JOIN fixtures f ON f.fixture_id = tm.fixture_id
)
SELECT
    f.fixture_id,
    f.kickoff_utc,
    f.home_id,
    f.away_id,
    -- rolling xG over the home team's prior matches (strictly before kickoff)
    (SELECT avg(xg_for)     FROM team_gw t
        WHERE t.team_id = f.home_id AND t.kickoff_utc < f.kickoff_utc) AS home_xg_for,
    (SELECT avg(xg_against) FROM team_gw t
        WHERE t.team_id = f.home_id AND t.kickoff_utc < f.kickoff_utc) AS home_xg_against,
    (SELECT avg(xg_for)     FROM team_gw t
        WHERE t.team_id = f.away_id AND t.kickoff_utc < f.kickoff_utc) AS away_xg_for,
    (SELECT avg(xg_against) FROM team_gw t
        WHERE t.team_id = f.away_id AND t.kickoff_utc < f.kickoff_utc) AS away_xg_against
FROM fixtures f
WHERE f.season = ?
ORDER BY f.kickoff_utc;
"""


def build_team_features(season: str | None = None, con=None):  # noqa: ANN001
    """Return a DataFrame of point-in-time team form features for the season."""
    season = season or config.SEASON
    owns = con is None
    con = con or duck.connect(read_only=True)
    try:
        return con.execute(TEAM_FORM_SQL, [season]).df()
    finally:
        if owns:
            con.close()


# TODO(phase-1): add player-level features (opponent-adjusted xG/xGA shares,
# minutes/rotation trends, set-piece & penalty-taker flags, home/away splits) and
# a fixture-difficulty feature derived from the match engine's own probabilities.
