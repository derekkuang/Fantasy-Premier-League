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
            # Everything the caller needs to decide whether this artifact is fit to publish.
            # A dropped source season used to be invisible from here.
            "source": out.get("source_report", {}),
        },
        # JSON object keys must be strings; the API normalises team ids back to int on read.
        "fpl_teams": {str(tid): name for tid, name in out["fpl_teams"].items()},
        "records": out["records"],
        "fixture_ticker": {str(tid): rows for tid, rows in out["fixture_ticker"].items()},
        "matches": out["matches"],
    }


# Health thresholds for a SCHEDULED run. These are refusal points, not warnings: the failure
# this guards against is not a crash, it is every number getting quietly worse while the job
# keeps exiting 0. docs/HANDOFF.md §4 called it the one thing that will silently rot a deployed
# site, and it had been true since 2026-08-03.
MAX_FALLBACK_FIXTURES = 3   # 2 is healthy (promoted sides the engine has no history for)
MIN_RECORDS = 400           # a real gameweek carries ~550
# Exactly three clubs are promoted each season and a promoted club has no top-flight history, so
# it CANNOT be mapped to the engine's teams and correctly falls back to the promoted-side prior.
# Up to three unmapped teams is therefore the normal state, not a fault. More than three means
# the name mapping itself has broken — a rename the fuzzy matcher no longer resolves — which is
# a different thing and worth stopping for.
MAX_UNMAPPED_TEAMS = 3


def next_gameweek() -> int:
    """The gameweek to precompute, resolved from the landed bootstrap — never hardcoded.

    A scheduler passing a literal gameweek number goes stale the moment one completes, and the
    failure is quiet: the site keeps serving a past week's projections as if they were current.
    FPL's own `is_next` flag is the authority; the deadline comparison is the fallback for a
    bootstrap captured mid-transition, when the flags can briefly be stale.
    """
    from ..storage import load as storeload

    boot = storeload.latest_raw("fpl_api", "bootstrap")
    events = boot.get("events") or []
    for e in events:
        if e.get("is_next"):
            return int(e["id"])
    now = datetime.now(UTC)
    upcoming = [
        int(e["id"]) for e in events
        if e.get("deadline_time")
        and datetime.fromisoformat(e["deadline_time"]) > now
    ]
    if upcoming:
        return min(upcoming)
    raise RuntimeError(
        "no upcoming gameweek in the landed bootstrap — season over, or the bootstrap is stale; "
        "re-run scripts/pull_data.py before precomputing"
    )


def health_check(meta: dict) -> list[str]:
    """Reasons this artifact should NOT be published. Empty means healthy.

    Pure and separately tested, because the whole point is that it fires on a machine nobody is
    watching and a threshold that is wrong in the lenient direction is worse than none at all.
    """
    problems = []
    source = meta.get("source") or {}
    failed = source.get("failed") or []
    if failed:
        seasons = ", ".join(f.get("season") or f.get("code", "?") for f in failed)
        problems.append(
            f"{len(failed)} source season(s) failed to download ({seasons}) — the engine fitted "
            "on less history than intended"
        )
    unmapped = source.get("unmapped_teams") or []
    if len(unmapped) > MAX_UNMAPPED_TEAMS:
        problems.append(
            f"{len(unmapped)} unmapped teams ({', '.join(unmapped)}) — more than the three "
            "promoted clubs, so the name mapping has probably broken rather than this being "
            "the usual promoted-side fallback"
        )
    fb = meta.get("fallback_fixtures")
    if isinstance(fb, int) and fb > MAX_FALLBACK_FIXTURES:
        problems.append(
            f"fallback_fixtures={fb} exceeds {MAX_FALLBACK_FIXTURES} — more fixtures than "
            "expected are being priced without engine history"
        )
    n = meta.get("n_records")
    if isinstance(n, int) and n < MIN_RECORDS:
        problems.append(f"only {n} player records (expected >= {MIN_RECORDS})")
    return problems


# Sanity thresholds for the PUBLISH gate — a second, different kind of check. `health_check`
# reads the fit's own report of its inputs; this compares the new artifact against the one
# CURRENTLY BEING SERVED, and exists for the failure the first check cannot see: a fit whose
# inputs all look fine but whose output is degenerate. The thresholds are wide on purpose —
# projections legitimately move week to week — so a trip means "grossly wrong", not "different".
MAX_RECORD_DROP = 0.5   # new artifact has lost more than half the players the live one carries
MIN_XP_MEAN_RATIO = 0.3  # mean projection collapsed to under 30% of the live artifact's
MIN_NONZERO_XP_SHARE = 0.5  # over half the projections are exactly zero


def publish_gate(new_payload: dict, current_payload: dict | None) -> list[str]:
    """Reasons the new artifact must not REPLACE the currently-served one. Empty means go.

    `current_payload` is None on a first publish — there is nothing to regress against, so the
    only checks that run are the absolute ones. That asymmetry is deliberate: a cold start
    should not be blocked by the absence of history.
    """
    problems = []
    new_recs = new_payload.get("predictions") or []
    xps = [float(r.get("xp") or 0.0) for r in new_recs]
    if xps:
        nonzero = sum(1 for x in xps if x > 0) / len(xps)
        if nonzero < MIN_NONZERO_XP_SHARE:
            problems.append(
                f"only {nonzero:.0%} of projections are non-zero — the fit is degenerate, "
                "whatever its inputs claimed"
            )
    if current_payload is not None:
        cur_recs = current_payload.get("predictions") or []
        if cur_recs and len(new_recs) < len(cur_recs) * MAX_RECORD_DROP:
            problems.append(
                f"record count fell {len(cur_recs)} -> {len(new_recs)} — more than half the "
                "players the live artifact serves would vanish"
            )
        cur_xps = [float(r.get("xp") or 0.0) for r in cur_recs]
        if xps and cur_xps:
            new_mean, cur_mean = sum(xps) / len(xps), sum(cur_xps) / len(cur_xps)
            if cur_mean > 0 and new_mean < cur_mean * MIN_XP_MEAN_RATIO:
                problems.append(
                    f"mean projection collapsed {cur_mean:.2f} -> {new_mean:.2f} — a real "
                    "week does not do that; a broken fit does"
                )
    return problems


def run(gw: int, horizon: int = 8, run_ts: str | None = None,
        narrate: bool = True, allow_degraded: bool = False) -> dict:
    """Precompute, GATE, then publish. Returns {path, meta, problems, published}.

    THE ORDER IS THE POINT, and it changed. This used to write the artifact first and let the
    caller health-check afterwards — correct when "writing" meant a local file a human would
    inspect before deploying, and silently wrong from the moment `store.write_gw` began
    publishing straight to the S3 the live API serves. From then on, "written either way so you
    can inspect it" actually meant "served to users either way". Now nothing reaches the store
    until both gates pass; a blocked artifact is returned to the caller for inspection instead
    of being published as a side effect.
    """
    payload = build_payload(gw, horizon=horizon, run_ts=run_ts, narrate=narrate)
    problems = health_check(payload["meta"])
    problems += publish_gate(payload, store.read_gw(gw))
    if problems and not allow_degraded:
        return {"path": None, "meta": payload["meta"], "payload": payload,
                "problems": problems, "published": False}
    path = store.write_gw(gw, payload)
    return {"path": str(path), "meta": payload["meta"], "problems": problems, "published": True}
