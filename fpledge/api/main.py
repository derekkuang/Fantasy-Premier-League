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

import json
import os
import threading
import time
from collections import Counter

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from .. import config
from ..balance import check_balance
from ..differentials import find_differentials
from ..models.optimizer import best_xi
from ..playermeta import EMPTY_META
from ..transfers import suggest_transfers
from . import store

app = FastAPI(
    title="fpledge API",
    version="0.1.0",
    description="Honest FPL expected-points + tooling. Not affiliated with the Premier League.",
)

# Read-only public data + GET only, and the frontend fetches server-side (so CORS is
# usually unused) — but keep it configurable: set FPLEDGE_CORS_ORIGINS to the real frontend
# origin(s) in prod (comma-separated). Defaults to "*" for local dev.
_cors_env = os.environ.get("FPLEDGE_CORS_ORIGINS", "*").strip()
_cors_origins = ["*"] if _cors_env in ("", "*") else [o.strip() for o in _cors_env.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)

from ..advisor.agent import MODEL as _ADVISOR_MODEL

_WEEKLY_CACHE = "public, max-age=3600"   # precomputed data changes ~weekly
_TEAM_CACHE = "public, max-age=120"       # a manager's picks change occasionally


# --- FPL client: ONE shared, throttled client (overridden in tests to avoid network) --- #
# A per-request client would open a new Session and, worse, reset the throttle state, so a
# public deploy could fire unbounded concurrent requests at fantasy.premierleague.com and
# get the host IP blocked. A single shared client serialises + rate-limits those calls.
_client_lock = threading.Lock()
_shared_client = None


def get_fpl_client():
    global _shared_client
    if _shared_client is None:
        with _client_lock:
            if _shared_client is None:
                from ..ingest.fpl_api import FPLClient
                _shared_client = FPLClient()
    return _shared_client


# Short-TTL cache of a manager's picks, guarded by a lock so concurrent /team requests
# don't stampede the FPL API (and repeat/abusive entry-id sweeps mostly hit the cache).
_PICKS_TTL_S = 120.0
_picks_lock = threading.Lock()
_picks_cache: dict[tuple[int, int], tuple[float, dict]] = {}


def _cached_picks(client, entry_id: int, gw: int) -> dict:
    key = (entry_id, gw)
    hit = _picks_cache.get(key)
    if hit and time.monotonic() - hit[0] < _PICKS_TTL_S:
        return hit[1]
    with _picks_lock:  # serialise outbound FPL calls; re-check the cache inside the lock
        hit = _picks_cache.get(key)
        if hit and time.monotonic() - hit[0] < _PICKS_TTL_S:
            return hit[1]
        summary = client.picks_summary(entry_id, gw)  # throttled inside the client
        _picks_cache[key] = (time.monotonic(), summary)
        return summary


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
        "captain_score": round(r.get("captain_score", 0.0), 2),
        # what NOT owning them costs against the field — the mirror of diff_value
        "template_risk": round(r.get("template_risk", 0.0), 2),
        # the same trade-off banded 1 (template) .. 5 (deep punt), for display
        "risk_tier": r.get("risk_tier", 3),
        "risk_label": r.get("risk_label", ""),
        # multi-gameweek outlook (default to this GW if a record predates the field)
        "xp_next3": round(r.get("xp_next3", r["xp"]), 2),
        "fixtures": r.get("fixtures", []),  # [{gw, opp, home, xp, fdr}, ...]
        "breakdown": r.get("breakdown"),    # per-term xP split for the sheet (may be None)
        **_context(r),
    }


def _context(r: dict) -> dict:
    """The descriptive bundle (why a projection looks the way it does). Defaults keep the
    response shape total for records precomputed before these fields existed.
    """
    return {
        "availability": r.get("availability", EMPTY_META["availability"]),
        "recent": r.get("recent", EMPTY_META["recent"]),
        "price_moves": r.get("price_moves", EMPTY_META["price_moves"]),
        "set_pieces": r.get("set_pieces", EMPTY_META["set_pieces"]),
    }


def _project_player(p: dict) -> dict:
    """Compact player view for a transfer's out/in and squad rows."""
    return {
        "element_id": p["id"], "web_name": p["name"], "team": p["team_name"],
        "price": p["price"], "xp": round(p["xp"], 2),
    }


DEMO_BUDGET = 100.0   # the FPL starting budget the sample squad must fit inside


def _demo_picks(records: list[dict]) -> dict:
    """A sample 15-man squad — and a LEGAL one.

    This is the primary demo: in preseason the FPL API exposes no real squad, so every visitor
    who hasn't got a team id sees this. An earlier version took the top 2/5/5/3 by xP with no
    constraints, which produced a £116.5m side containing four Arsenal players — impossible
    under the game's rules, and obvious at a glance to anyone who plays it.

    Greedy by xP subject to all three real constraints, with a lookahead so an expensive early
    pick can't leave the remaining slots unaffordable.
    """
    quota = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
    pool = sorted(
        (r for r in records if not r["low_cov"] and r["price"]),
        key=lambda r: r["xp"], reverse=True,
    )
    cheapest = {
        pos: min((r["price"] for r in pool if r["position"] == pos), default=0.0)
        for pos in quota
    }

    need = dict(quota)
    clubs: Counter = Counter()
    ids: list[int] = []
    spend = 0.0
    for r in pool:
        pos = r["position"]
        if need.get(pos, 0) == 0 or clubs[r["team_id"]] >= 3:
            continue
        # could we still fill every remaining slot at the cheapest going rate after this?
        after = {**need, pos: need[pos] - 1}
        floor = sum(cheapest[p] * n for p, n in after.items())
        if spend + r["price"] + floor > DEMO_BUDGET:
            continue
        ids.append(r["element_id"])
        spend += r["price"]
        need[pos] -= 1
        clubs[r["team_id"]] += 1
        if not sum(need.values()):
            break

    return {"element_ids": ids, "captain": None, "vice_captain": None,
            "bank": round(DEMO_BUDGET - spend, 1), "squad_value": round(spend, 1)}


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


@app.get("/model")
def model_card(response: Response) -> dict:
    """How well the model actually does, measured rather than asserted.

    Served from an artifact `scripts/build_model_card.py` writes, so the honesty page can
    never drift from what was last measured — if the number on the page is stale, the
    artifact is stale, and its `generated_at` says so out loud.

    404 rather than a placeholder when it hasn't been generated: a page claiming to publish
    the model's accuracy must not invent it.
    """
    path = config.DATA_DIR / "eval" / "model_card.json"
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="No model card yet — run `python scripts/build_model_card.py`.",
        )
    response.headers["Cache-Control"] = _WEEKLY_CACHE
    return json.loads(path.read_text())


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


@app.get("/matches/{gw}")
def matches(gw: int, response: Response) -> dict:
    """Every fixture in the precomputed window with its scoreline distribution."""
    payload = _load_or_404(gw)
    response.headers["Cache-Control"] = _WEEKLY_CACHE
    return {"meta": payload["meta"], "matches": payload.get("matches", [])}


@app.get("/matches/{gw}/{match_id}")
def match(gw: int, match_id: str, response: Response) -> dict:
    """One fixture: the scoreline distribution, the projected XIs, and every FPL asset in it.

    `assets` is both clubs' players ranked by xP for THIS gameweek — the "who do I own from
    this game" view. It is only meaningful for the current gameweek, so it is attached only
    when the requested match is in it.
    """
    payload = _load_or_404(gw)
    response.headers["Cache-Control"] = _WEEKLY_CACHE
    found = next((m for m in payload.get("matches", []) if m["match_id"] == match_id), None)
    if found is None:
        raise HTTPException(status_code=404, detail=f"No match {match_id!r} in GW{gw}.")

    assets: list[dict] = []
    if found["gw"] == gw:
        sides = {found["home_id"], found["away_id"]}
        assets = sorted(
            (_project_prediction(r) for r in payload["records"] if r["team_id"] in sides),
            key=lambda r: r["xp"], reverse=True,
        )
    return {"meta": payload["meta"], "match": found, "assets": assets}


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
    client=Depends(get_fpl_client),
) -> dict:
    payload = _load_or_404(gw)
    response.headers["Cache-Control"] = _TEAM_CACHE
    records = payload["records"]

    if entry_id == 0:  # reserved id: a sample team, no FPL API call (see _demo_picks)
        picks = _demo_picks(records)
    else:
        try:
            picks = _cached_picks(client, entry_id, gw)
        except Exception as exc:
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
            "template_risk": round(rec.get("template_risk", 0.0), 2),
            "risk_tier": rec.get("risk_tier", 3),
            "risk_label": rec.get("risk_label", ""),
            "captain_score": round(rec.get("captain_score", 0.0), 2),
            "breakdown": rec.get("breakdown"),  # the per-term xP split (may be None)
            "is_starter": p["id"] in starter_ids,
            "is_captain": p["id"] == captain_id,
            # a squad row is exactly where "why is he on 0.00?" gets asked
            **_context(rec),
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


# --- advisor ------------------------------------------------------------------------ #
# The one endpoint that costs money per call, so it is the one endpoint that refuses to
# pretend. No client configured => 503 with the reason, never a canned answer that looks
# like the feature working.

_ADVISOR_MAX_MESSAGE = 600        # a question, not a pasted essay
_ADVISOR_MAX_HISTORY = 24         # ~12 exchanges; the loop resends all of it every turn
_ADVISOR_WINDOW_S = 3600.0
_ADVISOR_PER_WINDOW = 4           # placeholder for the real per-manager gameweek quota

_advisor_lock = threading.Lock()
_advisor_hits: dict[str, list[float]] = {}


def _advisor_client():
    """The Anthropic client, the scripted stub, or None. Never a silent no-op."""
    if os.environ.get("FPLEDGE_ADVISOR_STUB") == "1":
        from ..advisor.stub import StubClient
        return StubClient(), True
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None, False
    try:
        import anthropic
    except ImportError:
        return None, False
    return anthropic.Anthropic(), False


def _jsonable(obj):
    """Flatten SDK content blocks into plain JSON.

    The conversation has to round-trip through the browser — the Messages API is stateless,
    so continuing a chat means resending every prior turn including the assistant's tool_use
    blocks. Those arrive as SDK objects, which FastAPI cannot serialise. Plain dicts both
    serialise and are accepted back by the API unchanged, so this loses nothing.
    """
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if hasattr(obj, "model_dump"):          # anthropic SDK blocks are pydantic models
        return _jsonable(obj.model_dump())
    if hasattr(obj, "__dict__"):            # the scripted stub's blocks are plain objects
        return {k: _jsonable(v) for k, v in vars(obj).items()}
    return obj


def _advisor_rate_limit(key: str) -> None:
    """In-process, per-IP, best-effort.

    NOT the real quota. The real one is per manager per gameweek and needs a database that
    this app does not have yet (see docs/HANDOFF.md §6). This exists so that shipping the
    endpoint cannot produce an unbounded bill in the window before that lands, and it dies
    with the process — a second worker doubles the ceiling.
    """
    now = time.monotonic()
    with _advisor_lock:
        hits = [t for t in _advisor_hits.get(key, []) if now - t < _ADVISOR_WINDOW_S]
        if len(hits) >= _ADVISOR_PER_WINDOW:
            raise HTTPException(
                status_code=429,
                detail=f"Advisor limit reached ({_ADVISOR_PER_WINDOW} per hour while this is "
                       "in preview). Try again later.",
            )
        hits.append(now)
        _advisor_hits[key] = hits


@app.get("/advise")
def advise_status() -> dict:
    """Whether the advisor can actually answer, so the UI can say so before anyone types."""
    client, stub = _advisor_client()
    return {
        "available": client is not None,
        "stub": stub,
        "model": _ADVISOR_MODEL,
        "reason": None if client else (
            "The advisor needs an ANTHROPIC_API_KEY and the `anthropic` package "
            '(pip install -e ".[llm]"). It is switched off rather than faked.'
        ),
    }


@app.post("/advise")
def advise_endpoint(body: dict, request: Request) -> dict:
    """One conversational turn about a squad.

    Takes either an `entry_id` (fetched from FPL) or an explicit `owned` list of element ids,
    so a squad built in the browser can be advised on exactly like a real one.
    """
    client, stub = _advisor_client()
    if client is None:
        raise HTTPException(status_code=503, detail=advise_status()["reason"])

    message = str(body.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")
    if len(message) > _ADVISOR_MAX_MESSAGE:
        raise HTTPException(
            status_code=400,
            detail=f"Keep it under {_ADVISOR_MAX_MESSAGE} characters — this is a question box, "
                   "not a document upload.",
        )
    history = body.get("history") or []
    if not isinstance(history, list) or len(history) > _ADVISOR_MAX_HISTORY:
        raise HTTPException(status_code=400, detail="history too long — start a new conversation")

    gw = int(body.get("gw") or 0)
    payload = _load_or_404(gw)
    records = payload["records"]

    owned = body.get("owned")
    if owned:
        owned_ids = [int(e) for e in owned][:15]
        bank = float(body.get("bank") or 0.0)
        free_transfers = int(body.get("free_transfers") or 0)
    else:
        entry_id = int(body.get("entry_id") or 0)
        picks = _demo_picks(records) if entry_id == 0 else _cached_picks(get_fpl_client(), entry_id, gw)
        owned_ids = list(picks["element_ids"])
        bank = picks["bank"]
        free_transfers = int(body.get("free_transfers") or 1)

    if len(owned_ids) < 11:
        raise HTTPException(status_code=400, detail="need a squad of at least 11 known players")

    _advisor_rate_limit(request.client.host if request.client else "unknown")

    from ..advisor.agent import advise
    from ..advisor.tools import AdvisorTools

    tools = AdvisorTools(
        records, owned_ids, bank=bank, free_transfers=free_transfers,
        ticker={str(k): v for k, v in payload.get("fixture_ticker", {}).items()},
    )
    result = advise(tools, message, history=history, client=client)
    return {
        "reply": result["reply"],
        "history": _jsonable(result["messages"]),
        "tool_calls": result["tool_calls"],
        "usage": result["usage"],
        "cost_usd": result["cost_usd"],
        "stopped_at_limit": result["stopped_at_limit"],
        "stub": stub,
    }
