"""Precompute job — the once-per-refresh batch the API reads from.

Runs the expensive Dixon-Coles fit ONCE (via `gw.assemble_for_serving`) and writes a
self-contained JSON artifact per gameweek: the per-player xP records AND the true-FDR
fixture ticker, tagged with model_ver + run_ts. The API never fits the engine or touches
DuckDB — it only reads these files. This is the AWS/MLOps slice from the roadmap: schedule
`run(gw)` weekly (EventBridge -> Fargate, or a platform cron) writing to the serving store.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ..gw import assemble_for_serving
from . import MODEL_VER, store


def build_payload(gw: int, horizon: int = 5, run_ts: str | None = None) -> dict:
    """Assemble the serving payload for a gameweek (no I/O side effects besides the fit).

    Raises RuntimeError if there is no player data for the configured season.
    """
    out = assemble_for_serving(gw, horizon=horizon)
    if out is None:
        raise RuntimeError(
            "no player_season data for the configured season — run "
            "scripts/build_db.py + scripts/pull_player_history.py first."
        )
    ts = run_ts or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "meta": {
            "gw": gw,
            "horizon": horizon,
            "model_ver": MODEL_VER,
            "run_ts": ts,
            "n_records": len(out["records"]),
            "fallback_fixtures": len(out["fallback"]),
        },
        # JSON object keys must be strings; the API normalises team ids back to int on read.
        "fpl_teams": {str(tid): name for tid, name in out["fpl_teams"].items()},
        "records": out["records"],
        "fixture_ticker": {str(tid): rows for tid, rows in out["fixture_ticker"].items()},
    }


def run(gw: int, horizon: int = 5, run_ts: str | None = None) -> dict:
    """Precompute + persist the serving artifact for a gameweek. Returns {path, meta}."""
    payload = build_payload(gw, horizon=horizon, run_ts=run_ts)
    path = store.write_gw(gw, payload)
    return {"path": str(path), "meta": payload["meta"]}
