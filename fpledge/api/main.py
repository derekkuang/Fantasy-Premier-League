"""FastAPI app: four read endpoints over the precomputed serving store.

    GET /health                       liveness + which gameweeks are precomputed
    GET /predictions/{gw}             precomputed per-player xP (projected read)
    GET /fixtures/{gw}?horizon=5      true-FDR fixture ticker grid
    GET /differentials/{gw}?...       low-owned, high-xP finder over the records
    GET /team/{entry_id}?gw={gw}      personalised: the manager's 15 + projection + best
                                      transfer + squad balance (the one non-cacheable route)

The engine is never fitted here — every route reads `api.store`. The one adapter that
matters: serving records are keyed element_id/web_name, but the optimizer/transfer/balance
functions expect id/name/team dicts, so `_pool_dict`/`_balance_dict` translate.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware

from ..balance import check_balance
from ..differentials import find_differentials
from ..models.optimizer import best_xi
from ..transfers import suggest_transfers
from . import store

app = FastAPI(
    title="fpledge API",
    version="0.1.0",
    description="Honest FPL expected-points + tooling. Not affiliated with the Premier League.",
)

# Phase 1 frontend (Next.js / HTMX) calls this from the browser. Wide-open for v1 (no
# secrets, read-only public data); tighten to the real frontend origin before prod.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

_WEEKLY_CACHE = "public, max-age=3600"   # precomputed data changes ~weekly
_TEAM_CACHE = "public, max-age=120"       # a manager's picks change occasionally


# --- dependency: the FPL client (overridden in tests to avoid network) ------------- #
def get_fpl_client():  # noqa: ANN201
    from ..ingest.fpl_api import FPLClient  # noqa: PLC0415
    return FPLClient()


# --- adapters: serving record -> the shape each engine function expects ------------- #
def _pool_dict(r: dict) -> dict:
    """Translate a serving record into the optimizer/transfer player shape (id/name/team)."""
    return {
        "id": r["element_id"], "name": r["web_name"], "position": r["position"],
        "price": r["price"], "team_id": r["team_id"], "team_name": r["team_name"],
        "xp": r["xp"], "ownership": r["ownership"], "x_minutes": r["x_minutes"],
    }


def _balance_dict(p: dict, *, starter: bool, captain: bool) -> dict:
    """Translate a pool dict into the check_balance player shape (needs `team`, flags)."""
    return {
        "name": p["name"], "position": p["position"], "price": p["price"],
        "team": p["team_name"], "xp": p["xp"], "ownership": p["ownership"],
        "x_minutes": p["x_minutes"], "starter": starter, "captain": captain,
    }


def _project_prediction(r: dict) -> dict:
    """The public per-player prediction shape (a projection of the full record)."""
    return {
        "element_id": r["element_id"], "web_name": r["web_name"], "position": r["position"],
        "team": r["team_name"], "price": r["price"], "xp": round(r["xp"], 2),
        "ownership": r["ownership"], "diff_value": round(r["diff_value"], 2),
        "x_minutes": round(r["x_minutes"], 1), "low_coverage": r["low_cov"],
    }


def _project_player(p: dict) -> dict:
    """Compact player view for a transfer's out/in and squad rows."""
    return {
        "element_id": p["id"], "web_name": p["name"], "team": p["team_name"],
        "price": p["price"], "xp": round(p["xp"], 2),
    }


def _demo_picks(records: list[dict]) -> dict:
    """A sample 15-man squad from the top precomputed players (2/5/5/3 by xP over the
    reliable pool). Lets the dashboard render without a real FPL id — useful in preseason
    (the API won't expose upcoming picks) and as a 'see a sample team' on the landing page.
    """
    quota = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
    by_pos: dict = {}
    for r in sorted(records, key=lambda r: r["xp"], reverse=True):
        if r["low_cov"] or not r["price"]:
            continue
        by_pos.setdefault(r["position"], []).append(r["element_id"])
    ids: list[int] = []
    for pos, n in quota.items():
        ids += by_pos.get(pos, [])[:n]
    return {"element_ids": ids, "captain": None, "vice_captain": None,
            "bank": 0.0, "squad_value": 0.0}


def _load_or_404(gw: int) -> dict:
    payload = store.read_gw(gw)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=f"GW{gw} not precomputed. Available: {store.available_gws() or 'none'}.",
        )
    return payload


# --- routes ------------------------------------------------------------------------ #
@app.get("/health")
def health() -> dict:
    return {"status": "ok", "available_gws": store.available_gws()}


@app.get("/predictions/{gw}")
def predictions(gw: int, response: Response) -> dict:
    payload = _load_or_404(gw)
    response.headers["Cache-Control"] = _WEEKLY_CACHE
    rows = sorted(payload["records"], key=lambda r: r["xp"], reverse=True)
    return {"meta": payload["meta"], "predictions": [_project_prediction(r) for r in rows]}


@app.get("/fixtures/{gw}")
def fixtures(gw: int, response: Response, horizon: int | None = Query(default=None, ge=1, le=10)) -> dict:
    payload = _load_or_404(gw)
    response.headers["Cache-Control"] = _WEEKLY_CACHE
    fpl_teams = payload["fpl_teams"]  # {str(team_id): name}
    limit_gw = gw + horizon if horizon else None
    teams = []
    for tid_str, rows in payload["fixture_ticker"].items():
        fx = [r for r in rows if limit_gw is None or r["gw"] < limit_gw]
        teams.append({
            "team_id": int(tid_str),
            "team_name": fpl_teams.get(tid_str),
            "fixtures": fx,
        })
    teams.sort(key=lambda t: (t["team_name"] or ""))
    return {"meta": payload["meta"], "start_gw": gw, "teams": teams}


@app.get("/differentials/{gw}")
def differentials(
    gw: int,
    response: Response,
    max_ownership: float = Query(default=15.0, ge=0, le=100),
    min_xp: float = Query(default=3.5, ge=0),
    position: str | None = Query(default=None),
    top: int = Query(default=15, ge=1, le=50),
) -> dict:
    payload = _load_or_404(gw)
    response.headers["Cache-Control"] = _WEEKLY_CACHE
    picks = find_differentials(
        payload["records"], max_ownership=max_ownership, min_xp=min_xp,
        position=position, top=top,
    )
    return {"meta": payload["meta"], "differentials": [_project_prediction(r) for r in picks]}


@app.get("/team/{entry_id}")
def team(
    entry_id: int,
    response: Response,
    gw: int = Query(..., description="gameweek to analyse (must be precomputed)"),
    free_transfers: int = Query(default=1, ge=0, le=5),
    client=Depends(get_fpl_client),  # noqa: ANN001
) -> dict:
    payload = _load_or_404(gw)
    response.headers["Cache-Control"] = _TEAM_CACHE
    records = payload["records"]

    if entry_id == 0:  # reserved id: a sample team, no FPL API call (see _demo_picks)
        picks = _demo_picks(records)
    else:
        try:
            picks = client.picks_summary(entry_id, gw)
        except Exception as exc:  # noqa: BLE001 — translate client/HTTP failures to friendly errors
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status == 404:
                # FPL only exposes a squad AFTER that gameweek's deadline, so before the
                # season's first deadline no team is fetchable for anyone (preseason).
                raise HTTPException(
                    status_code=404,
                    detail="No FPL squad is available for this gameweek yet. FPL only "
                    "reveals a manager's team after the gameweek deadline, so no team can "
                    "be loaded before the season's first deadline (preseason). If the "
                    "season is under way, this ID may be private or invalid. Meanwhile, "
                    "try the sample team.",
                ) from exc
            # Network error / FPL outage — not the caller's fault, so don't blame the id.
            raise HTTPException(
                status_code=502,
                detail="The FPL API is unavailable right now — please try again shortly.",
            ) from exc
    all_by_id = {r["element_id"]: _pool_dict(r) for r in records}
    rec_by_id = {r["element_id"]: r for r in records}  # for the per-player xP breakdown
    # Reliable transfer universe (drop promoted/low-coverage + priceless), then ensure the
    # manager's own scored players are lookupable so suggest_transfers can't KeyError.
    pool_by_id = {
        r["element_id"]: _pool_dict(r)
        for r in records if not r["low_cov"] and r["price"]
    }
    owned_ids = [e for e in picks["element_ids"] if e in all_by_id]
    unscored = [e for e in picks["element_ids"] if e not in all_by_id]
    for e in owned_ids:
        pool_by_id.setdefault(e, all_by_id[e])

    owned = [all_by_id[e] for e in owned_ids]
    xi = best_xi(owned)  # None if the scored subset can't field a legal XI

    projected_points = round(xi["total_xp"], 2) if xi else None
    starter_ids = set(xi["xi"]) if xi else set()
    captain_id = xi["captain"] if xi else None
    captain = next(
        ({"element_id": p["id"], "web_name": p["name"], "xp": round(p["xp"], 2)}
         for p in owned if p["id"] == captain_id),
        None,
    )

    def _squad_row(p: dict) -> dict:
        rec = rec_by_id.get(p["id"], {})
        return {
            **_project_player(p),
            "position": p["position"],
            "ownership": p["ownership"],
            "x_minutes": round(p["x_minutes"], 1),
            "diff_value": round(rec.get("diff_value", 0.0), 2),
            "captain_score": round(rec.get("captain_score", 0.0), 2),
            "breakdown": rec.get("breakdown"),  # the per-term xP split (may be None)
            "is_starter": p["id"] in starter_ids,
            "is_captain": p["id"] == captain_id,
        }

    squad = sorted(
        (_squad_row(p) for p in owned),
        key=lambda r: ({"GK": 0, "DEF": 1, "MID": 2, "FWD": 3}[r["position"]], -r["xp"]),
    )

    best_transfer = None
    if owned_ids:
        moves = suggest_transfers(
            owned_ids, pool_by_id, bank=picks["bank"],
            free_transfers=free_transfers, top=1,
        )
        if moves:
            m = moves[0]
            best_transfer = {
                "out": _project_player(m["out"]), "in": _project_player(m["in"]),
                "cost": m["cost"], "xp_gain": m["gain"], "net_gain": m["net"],
            }

    balance = None
    if xi:
        squad_players = [
            _balance_dict(p, starter=p["id"] in starter_ids, captain=p["id"] == captain_id)
            for p in owned
        ]
        balance = check_balance(squad_players)

    return {
        "meta": payload["meta"],
        "entry_id": entry_id,
        "gw": gw,
        "bank": picks["bank"],
        "free_transfers": free_transfers,
        "projected_points": projected_points,
        "captain": captain,
        "squad": squad,
        "best_transfer": best_transfer,
        "balance": balance,
        "unscored_elements": unscored,  # owned players with no prediction (promoted/low-data)
    }
