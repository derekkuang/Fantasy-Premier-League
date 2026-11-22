#!/usr/bin/env python3
"""Keeper save rounding (E5): the method and the rule are in `fpledge/eval/save_rounding.py`.

Usage: python scripts/compare_save_rounding.py             development seasons, both arms
       python scripts/compare_save_rounding.py --confirm   2026-27 GW12-15, once, after GW15 is final

Offline apart from public data fetches. Changes nothing in production.
"""

from __future__ import annotations

import json
import pathlib
import sys
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import compare_player_rates as cpr

from fpledge import config
from fpledge.eval import cards_assists as ca
from fpledge.eval import player_rates as pr
from fpledge.eval import save_rounding as sr
from fpledge.eval.fpl_backtest import validate_xp
from fpledge.models import starts

DEV_OUT = config.DATA_DIR / "eval" / "save_rounding_dev.json"
CONFIRM_OUT = config.DATA_DIR / "eval" / "save_rounding_confirm.json"
MODES = {"production": "linear", "floor": "floor"}


def _run(job: tuple[dict, str]) -> tuple[str, str, list, list]:
    """One arm on one season at production's settings: (season, arm, records, keeper rows)."""
    data, arm = job
    season = data["season"]
    keepers: list = []

    def sink(gw, el, row, bd):
        if row["position"] == "GK":
            keepers.append({"season": season, "gw": gw, "element": el,
                            "p_play": bd["p_play"], "projected": bd["save_points"],
                            "awarded": int(row.get("saves", 0)) // config.SAVES_PER_POINT})

    _m, records = validate_xp(
        data["rows"], data["fixtures"], data["teams"], burn_in=pr.BURN_IN,
        minutes_mode="starts", start_model=starts.load(),
        fixture_lambdas=data["lambdas"], prior_rates=data["priors"]["position"], prior_k=3,
        saves_per_goal=config.SAVES_PER_EXPECTED_GOAL, save_points_mode=MODES[arm],
        dc_mode="by_case", dc_size=config.DC_NB_SIZE,
        card_k=float("inf"), card_prior=ca.card_prior(data["previous"]),
        assist_scale=config.ASSIST_SCALE, breakdown_sink=sink, return_records=True)
    return season, arm, records, keepers


def _score(datasets: list[dict], gws: tuple[int, int] | None = None) -> dict:
    """{season: {arm: (records, keeper rows)}}, restricted to `gws` (inclusive) when given."""
    out: dict = {d["season"]: {} for d in datasets}
    with ProcessPoolExecutor(max_workers=6) as pool:
        for season, arm, records, keepers in pool.map(_run, [(d, a) for d in datasets for a in MODES]):
            if gws:
                records = [r for r in records if gws[0] <= r[0] <= gws[1]]
                keepers = [k for k in keepers if gws[0] <= k["gw"] <= gws[1]]
            out[season][arm] = (records, keepers)
    return out


def _compare(scored: dict) -> tuple[dict, dict, dict, dict]:
    """Per-season term gaps, and pooled keeper MSE / all-player Spearman, floor vs production."""
    by_season, mse, rho = {}, {a: {} for a in MODES}, {a: {} for a in MODES}
    for season, arms in scored.items():
        keys = {a: {(k["gw"], k["element"]) for k in arms[a][1]} for a in MODES}
        if keys["production"] != keys["floor"]:
            raise ValueError(f"{season}: the two arms projected different keeper fixtures")
        include = {(k["gw"], k["element"]) for k in arms["production"][1]
                   if k["p_play"] >= sr.EXPECTED_TO_PLAY}
        by_season[season] = {a: sr.term_gap(sr.term_sums(arms[a][1])) for a in MODES}
        for a in MODES:
            mse[a].update(ca.mse_by_gw(arms[a][0], season, include=include))
            rho[a].update(pr.gw_scores(arms[a][0], season))
    pooled = {a: sr.term_gap(sr.term_sums(k for arms in scored.values() for k in arms[a][1]))
              for a in MODES}
    return (by_season, pooled, ca.compare_mse(mse["production"], mse["floor"]),
            pr.compare(rho["production"], rho["floor"]))


def _gap(label: str, g: dict) -> str:
    return (f"{label:<11} projected {g['projected']:.3f} awarded {g['awarded']:.3f}  "
            f"gap {g['gap']:+.3f} [{g['ci'][0]:+.3f}, {g['ci'][1]:+.3f}]"
            f"{'' if sr.reaches(g['ci']) else '  (clear of tolerance)'}")


def _others(mse: dict, rho: dict) -> None:
    print(f"  keeper squared error {mse['mse_a']:.3f} -> {mse['mse_b']:.3f}  diff {mse['diff']:+.4f} "
          f"[{mse['ci'][0]:+.4f}, {mse['ci'][1]:+.4f}]  keeper bias "
          f"{mse['bias_a'].get('GK', 0):+.3f} -> {mse['bias_b'].get('GK', 0):+.3f}  ({mse['n_rows']} rows)")
    print(f"  all-player ρ {rho['rho_a']:.4f} -> {rho['rho_b']:.4f}  diff {rho['diff']:+.4f} "
          f"[{rho['ci'][0]:+.4f}, {rho['ci'][1]:+.4f}]")


def development() -> None:
    by_season, pooled, mse, rho = _compare(_score([cpr.load_season(*s) for s in cpr.DEV]))
    print("\nsave term, keepers expected to start (awarded - projected per fixture):")
    for season, gaps in by_season.items():
        for a in MODES:
            print(f"  {season} " + _gap(a, gaps[a]))
    for a in MODES:
        print("  pooled  " + _gap(a, pooled[a]))
    print("\nfloor against production, pooled:")
    _others(mse, rho)
    choice = sr.development(by_season, mse, rho)
    print(f"\nrule 1 (every season): {choice['rule1']}\nrule 2 (keeper squared error): "
          f"{choice['rule2']}\nrule 3 (ranking guard): {choice['rule3']}")
    print(f"proceed to confirmation: {choice['proceed']}")
    DEV_OUT.parent.mkdir(parents=True, exist_ok=True)
    DEV_OUT.write_text(json.dumps({"by_season": by_season, "pooled": pooled, "mse": mse,
                                   "spearman": rho, "choice": choice}, indent=2))
    print(f"\nwrote {DEV_OUT}")


def confirm() -> None:
    if CONFIRM_OUT.exists():
        raise SystemExit(f"{CONFIRM_OUT} exists, so this test has been run. See the rule in "
                         "fpledge/eval/save_rounding.py: a rerun needs a new pre-registration.")
    if not DEV_OUT.exists() or not json.loads(DEV_OUT.read_text())["choice"]["proceed"]:
        raise SystemExit("development has not passed: production stays.")
    data = cpr.load_this_season()
    last = max(r["gw"] for r in data["rows"])
    if last < sr.CONFIRM_GWS[1]:
        raise SystemExit(f"landed results run to GW{last}; the rule waits for GW{sr.CONFIRM_GWS[1]} "
                         "to be final.")
    scored = _score([data], gws=sr.CONFIRM_GWS)
    by_season, _pooled, mse, rho = _compare(scored)
    gaps = by_season[sr.CONFIRM_SEASON]
    decision = sr.verdict(gaps)
    lo, hi = sr.CONFIRM_GWS
    print(f"\nsave term, {sr.CONFIRM_SEASON} GW{lo}-{hi}, keepers expected to start:")
    for a in MODES:
        print("  " + _gap(a, gaps[a]))
    print(f"\nVERDICT: {decision}")
    print("\nreported, deciding nothing:")
    _others(mse, rho)
    CONFIRM_OUT.write_text(json.dumps({"gws": sr.CONFIRM_GWS, "gaps": gaps, "verdict": decision,
                                       "descriptive": {"mse": mse, "spearman": rho}}, indent=2))
    print(f"wrote {CONFIRM_OUT}")


if __name__ == "__main__":
    if "--confirm" in sys.argv[1:]:
        confirm()
    else:
        development()
