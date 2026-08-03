"""Precompute job — the once-per-refresh batch the API reads from.

Runs the expensive Dixon-Coles fit ONCE (via `gw.assemble_for_serving`) and writes a
self-contained JSON artifact per gameweek: the per-player xP records AND the true-FDR
fixture ticker, tagged with model_ver + run_ts. The API never fits the engine or touches
DuckDB — it only reads these files. This is the AWS/MLOps slice from the roadmap: schedule
`run(gw)` weekly (EventBridge -> Fargate, or a platform cron) writing to the serving store.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ..brief import brief_matches
from ..gw import assemble_for_serving
from . import MODEL_VER, store


def _assets_by_match(matches: list[dict], records: list[dict]) -> dict:
    """{match_id: that fixture's players, best xP first} for the current gameweek only."""
    if not matches:
        return {}
    gw = min(m["gw"] for m in matches)
    by_team: dict = {}
    for r in records:
        by_team.setdefault(r["team_id"], []).append(r)
    out: dict = {}
    for m in matches:
        if m["gw"] != gw:
            continue
        pool = by_team.get(m["home_id"], []) + by_team.get(m["away_id"], [])
        out[m["match_id"]] = [
            {"web_name": r["web_name"], "team": r["team_name"], "position": r["position"],
             "xp": round(r["xp"], 2), "price": r["price"], "ownership": r["ownership"]}
            for r in sorted(pool, key=lambda r: r["xp"], reverse=True)
        ]
    return out


def build_payload(gw: int, horizon: int = 8, run_ts: str | None = None,
                  narrate: bool = True) -> dict:
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

    # Written briefings for this gameweek's fixtures. Kept in the batch layer, not the engine:
    # `assemble_for_serving` stays pure, and a narration failure can never break a precompute.
    n_briefs = 0
    if narrate:
        n_briefs = brief_matches(out["matches"], _assets_by_match(out["matches"], out["records"]))

    return {
        "meta": {
            "gw": gw,
            "horizon": horizon,
            "model_ver": MODEL_VER,
            "run_ts": ts,
            "n_records": len(out["records"]),
            "n_matches": len(out["matches"]),
            "n_briefs": n_briefs,
            "fallback_fixtures": len(out["fallback"]),
        },
        # JSON object keys must be strings; the API normalises team ids back to int on read.
        "fpl_teams": {str(tid): name for tid, name in out["fpl_teams"].items()},
        "records": out["records"],
        "fixture_ticker": {str(tid): rows for tid, rows in out["fixture_ticker"].items()},
        "matches": out["matches"],
    }


def run(gw: int, horizon: int = 8, run_ts: str | None = None,
        narrate: bool = True) -> dict:
    """Precompute + persist the serving artifact for a gameweek. Returns {path, meta}."""
    payload = build_payload(gw, horizon=horizon, run_ts=run_ts, narrate=narrate)
    path = store.write_gw(gw, payload)
    return {"path": str(path), "meta": payload["meta"]}
