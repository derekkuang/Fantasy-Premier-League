#!/usr/bin/env python3
"""Should player rates update in-season? The method and the rule are in `fpledge/eval/player_rates.py`.

Usage: python scripts/compare_player_rates.py              development seasons, every variant
       python scripts/compare_player_rates.py --held-out   2026-27, the chosen candidate; once only

Offline. Reads vaastav's published seasons, football-data's closing odds and, for 2026-27, the
gameweek results `pull_data.py` has landed. Changes nothing in production.
"""

from __future__ import annotations

import json
import pathlib
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpledge import config
from fpledge.eval import player_rates as pr
from fpledge.eval import snapshots
from fpledge.eval.fpl_backtest import validate_xp
from fpledge.ingest import footballdata, vaastav
from fpledge.storage import load as storeload

DEV = [("2023-24", "2022-23", "2324"), ("2024-25", "2023-24", "2425"), ("2025-26", "2024-25", "2526")]
HELD_OUT = ("2026-27", "2025-26", "2627")
DEV_OUT = config.DATA_DIR / "eval" / "player_rates_dev.json"
HELD_OUT_OUT = config.DATA_DIR / "eval" / "player_rates_held_out.json"
_POS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def variants() -> dict:
    out = {"production": {"prior": "zero", "prior_k": None}, "this season": {"prior": None}}
    for k in pr.K_GRID:
        out[pr.blend_name(k)] = {"prior": "position", "prior_k": k}
        out[pr.blend_name(k, recent=True)] = {"prior": "position", "prior_k": k,
                                              "rate_half_life": pr.RECENCY_HALF_LIFE}
    return out


def _lambdas(fd_code: str, teams: dict, fixtures: list[dict]) -> dict:
    matches, report = footballdata.load_seasons_report([fd_code])
    if report["failed"]:
        raise SystemExit(f"football-data {fd_code} unavailable: {report['failed']}")
    lambdas = pr.market_fixture_lambdas(matches, teams)
    played = {(int(f["home"]), int(f["away"])) for f in fixtures}
    missing = played - set(lambdas)
    print(f"  closing odds price {len(played) - len(missing)} of {len(played)} played fixtures")
    if len(missing) > len(played) * 0.02:
        raise SystemExit(f"too many fixtures without odds: {sorted(missing)[:5]}")
    return lambdas


def load_season(season: str, previous: str, fd_code: str) -> dict:
    print(f"loading {season} (prior from {previous})...", flush=True)
    rows = vaastav.fetch_player_gws(season)
    fixtures = vaastav.fetch_fixtures(season)
    teams = vaastav.fetch_teams(season)
    players = {p["element"]: (p["code"], p["position"]) for p in vaastav.fetch_players_raw(season)}
    return _bundle(season, rows, fixtures, teams, players, previous, fd_code)


def load_this_season() -> dict:
    """2026-27 from our own landed data: vaastav's copy stops at GW6, ours runs to the last final GW."""
    import requests

    season, previous, fd_code = HELD_OUT
    boot = requests.get("https://fantasy.premierleague.com/api/bootstrap-static/", timeout=60).json()
    all_fixtures = requests.get("https://fantasy.premierleague.com/api/fixtures/", timeout=60).json()
    live = storeload.landed_event_live(season=season)
    gws = sorted(live)
    if gws != list(range(1, gws[-1] + 1)):
        raise SystemExit(f"landed gameweeks have gaps: {gws}")
    print(f"loading {season} GW1-{gws[-1]} from landed results (prior from {previous})...", flush=True)

    team_name = {t["id"]: t["name"] for t in boot["teams"]}
    elements = {e["id"]: e for e in boot["elements"]}
    games: dict = defaultdict(list)
    fixtures = []
    for f in all_fixtures:
        if f["event"] in live and f["finished"]:
            games[(f["event"], f["team_h"])].append((f["team_a"], True))
            games[(f["event"], f["team_a"])].append((f["team_h"], False))
            fixtures.append({"gw": f["event"], "home": str(f["team_h"]), "away": str(f["team_a"]),
                             "home_goals": f["team_h_score"], "away_goals": f["team_a_score"],
                             "kickoff": f["kickoff_time"]})
    # FPL's ep_next only fills the baseline column the harness requires; it plays no part here.
    ep = snapshots.availability_map(snapshots.load_index())
    rows, skipped = [], 0
    for gw in gws:
        for e in live[gw]["elements"]:
            el = elements.get(e["id"])
            fixture = games.get((gw, el["team"]), []) if el else []
            if len(fixture) != 1:
                skipped += 1
                continue
            (opp, home), s = fixture[0], e["stats"]
            rows.append({
                "element": e["id"], "name": el["web_name"], "position": _POS[el["element_type"]],
                "team": team_name[el["team"]], "gw": gw, "opponent_team": opp, "was_home": home,
                "minutes": int(s["minutes"]), "starts": int(s["starts"]),
                "xg": float(s["expected_goals"]), "xa": float(s["expected_assists"]),
                "dc": int(s["defensive_contribution"]), "bonus": int(s["bonus"]),
                "total_points": int(s["total_points"]), "fpl_xp": 0.0,
                "fpl_xp_prev": ep.get((gw, e["id"]), {}).get("ep_next", 0.0),
            })
    print(f"  {len(rows)} player-gameweeks, {skipped} skipped (no single fixture that gameweek)")
    teams = {name: tid for tid, name in team_name.items()}
    players = {e["id"]: (e["code"], _POS[e["element_type"]]) for e in boot["elements"]}
    return _bundle(season, rows, fixtures, teams, players, previous, fd_code)


def _bundle(season, rows, fixtures, teams, players, previous, fd_code) -> dict:
    prev = vaastav.fetch_players_raw(previous)
    return {"season": season, "rows": rows, "fixtures": fixtures, "teams": teams,
            "lambdas": _lambdas(fd_code, teams, fixtures),
            "priors": {"zero": pr.priors(prev, players, "zero"),
                       "position": pr.priors(prev, players, "position")}}


def _run(job: tuple[dict, str, dict]) -> tuple[str, str, dict]:
    data, name, spec = job
    prior = data["priors"][spec["prior"]] if spec["prior"] else None
    _metrics, records = validate_xp(
        data["rows"], data["fixtures"], data["teams"], burn_in=pr.BURN_IN, minutes_mode="recent",
        fixture_lambdas=data["lambdas"], prior_rates=prior, prior_k=spec.get("prior_k"),
        rate_half_life=spec.get("rate_half_life"), return_records=True)
    return data["season"], name, pr.gw_scores(records, data["season"])


def _score_all(datasets: list[dict], specs: dict) -> dict:
    jobs = [(d, name, spec) for d in datasets for name, spec in specs.items()]
    scores: dict = defaultdict(dict)
    with ProcessPoolExecutor(max_workers=6) as pool:
        for _season, name, s in pool.map(_run, jobs):
            scores[name].update(s)
    return scores


def _line(label: str, r: dict) -> str:
    lo, hi = r["ci"]
    return (f"  {label:<22} ρ {r['rho_a']:.4f} -> {r['rho_b']:.4f}  diff {r['diff']:+.4f} "
            f"[{lo:+.4f}, {hi:+.4f}]  MAE {r['mae_a']:.3f} -> {r['mae_b']:.3f}  ({r['n_gws']} GWs)")


def development() -> None:
    datasets = [load_season(*s) for s in DEV]
    scores = _score_all(datasets, variants())
    print("\neach variant against production, development seasons pooled:")
    summary = {}
    for name in variants():
        if name == "production":
            continue
        r = pr.compare(scores["production"], scores[name])
        summary[name] = r
        print(_line(name, r))
    choice = pr.choose(scores)
    print(f"\nrule 1: k = {choice['k']}  (pooled ρ by k: "
          + ", ".join(f"{k}: {v:.4f}" for k, v in choice["k_pooled"].items()) + ")")
    print("rule 2:" + _line("recent vs plain", choice["recent_vs_plain"])[1:])
    print(f"candidate: {choice['candidate']}")
    print("rule 3:")
    print(_line("pooled", choice["vs_production"]))
    for season, r in choice["by_season"].items():
        print(_line(season, r))
    print(f"proceed to held-out: {choice['proceed']}")
    DEV_OUT.parent.mkdir(parents=True, exist_ok=True)
    DEV_OUT.write_text(json.dumps({"choice": choice, "vs_production": summary}, indent=2))
    print(f"\nwrote {DEV_OUT}")


def held_out() -> None:
    if HELD_OUT_OUT.exists():
        raise SystemExit(f"{HELD_OUT_OUT} exists, so this test has been run. See the rule in "
                         "fpledge/eval/player_rates.py: a rerun needs a new pre-registration.")
    if not DEV_OUT.exists():
        raise SystemExit("run the development seasons first")
    choice = json.loads(DEV_OUT.read_text())["choice"]
    if not choice["proceed"]:
        raise SystemExit(f"{choice['candidate']} did not beat production on every development "
                         "season, so there is nothing to test. Production stays.")
    candidate = choice["candidate"]
    specs = {name: spec for name, spec in variants().items() if name in ("production", candidate)}
    data = load_this_season()
    scores = _score_all([data], specs)
    result = pr.compare(scores["production"], scores[candidate])
    stages = {
        label: pr.compare({k: v for k, v in scores["production"].items() if lo <= k[1] <= hi},
                          {k: v for k, v in scores[candidate].items() if lo <= k[1] <= hi})
        for label, lo, hi in (("GW2-5", 2, 5), ("GW6+", 6, 99))
    }
    decision = pr.verdict(result)
    HELD_OUT_OUT.write_text(json.dumps({"candidate": candidate, "result": result,
                                        "stages": stages, "verdict": decision}, indent=2))
    print(f"\n{candidate} against production, 2026-27:")
    print(_line("all", result))
    for label, r in stages.items():
        if r:
            print(_line(label, r))
    print(f"\nVERDICT: {decision}\nwrote {HELD_OUT_OUT}")


if __name__ == "__main__":
    if "--held-out" in sys.argv[1:]:
        held_out()
    else:
        development()
