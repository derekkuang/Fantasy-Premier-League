#!/usr/bin/env python3
"""Keeper save points: the method and the rule are in `fpledge/eval/keeper_saves.py`.

Usage: python scripts/compare_keeper_saves.py              development seasons, every variant
       python scripts/compare_keeper_saves.py --held-out   2022-23, the chosen candidate; once only

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
from fpledge.eval import keeper_saves as ks
from fpledge.eval import player_rates as pr
from fpledge.eval.fpl_backtest import validate_xp

DEV = cpr.DEV
HELD_OUT = ("2022-23", "2021-22", "2223")
DEV_OUT = config.DATA_DIR / "eval" / "keeper_saves_dev.json"
HELD_OUT_OUT = config.DATA_DIR / "eval" / "keeper_saves_held_out.json"


def _run(job: tuple[dict, str, float, str, bool]) -> tuple[str, str, dict, dict, list]:
    data, name, per_goal, mode, use_prior = job
    pairs: list = []

    def sink(_gw, _el, row, bd):
        if row["position"] == "GK":
            pairs.append((row["saves"], row["minutes"], bd["opp_lambda"]))

    _m, records = validate_xp(
        data["rows"], data["fixtures"], data["teams"], burn_in=pr.BURN_IN, minutes_mode="recent",
        fixture_lambdas=data["lambdas"],
        prior_rates=data["priors"]["position"] if use_prior else None,
        prior_k=3 if use_prior else None,
        saves_per_goal=per_goal, save_points_mode=mode, breakdown_sink=sink, return_records=True)
    season = data["season"]
    return season, name, pr.gw_scores(records, season), ks.keeper_errors(records, season), pairs


def _score(datasets: list[dict], specs: dict, use_prior: bool) -> tuple[dict, dict, list]:
    jobs = [(d, name, per_goal, mode, use_prior) for d in datasets
            for name, (per_goal, mode) in specs.items()]
    rho: dict = {name: {} for name in specs}
    gk: dict = {name: {} for name in specs}
    pairs: list = []
    with ProcessPoolExecutor(max_workers=6) as pool:
        for _season, name, r, k, p in pool.map(_run, jobs):
            rho[name].update(r)
            gk[name].update(k)
            if name == "production":
                pairs.extend(p)
    return rho, gk, pairs


def _line(label: str, k: dict, r: dict | None) -> str:
    out = (f"  {label:<12} keeper MAE {k['mae_a']:.3f} -> {k['mae_b']:.3f}  diff {k['diff']:+.3f} "
           f"[{k['ci'][0]:+.3f}, {k['ci'][1]:+.3f}]  bias {k['bias_a']:+.2f} -> {k['bias_b']:+.2f}")
    if r:
        out += (f"  | all ρ {r['rho_a']:.4f} -> {r['rho_b']:.4f} diff {r['diff']:+.4f} "
                f"[{r['ci'][0]:+.4f}, {r['ci'][1]:+.4f}]")
    return out


def _split(scores: dict, season: str) -> dict:
    return {k: v for k, v in scores.items() if k[0] == season}


def development() -> None:
    datasets = [cpr.load_season(*s) for s in DEV]
    _rho, _gk, pairs = _score(datasets, {"production": ks.VARIANTS["production"]}, use_prior=True)
    c = ks.fit_saves_per_goal(pairs)
    print(f"\nrule 1: c = {c} saves per expected goal conceded ({len(pairs)} keeper fixtures)")
    specs = {name: (per_goal or c, mode) for name, (per_goal, mode) in ks.VARIANTS.items()}
    rho, gk, _ = _score(datasets, specs, use_prior=True)
    keeper, spear, by_season = {}, {}, {}
    print("\neach variant against production, development seasons pooled:")
    for name in ("floor", "rate", "rate+floor"):
        keeper[name] = ks.compare_keepers(gk["production"], gk[name])
        spear[name] = pr.compare(rho["production"], rho[name])
        by_season[name] = {s: ks.compare_keepers(_split(gk["production"], s), _split(gk[name], s))
                           for s, _p, _f in DEV}
        print(_line(name, keeper[name], spear[name]))
    choice = ks.choose(keeper, spear, by_season)
    print(f"\nrule 2: eligible {choice['eligible']}, candidate {choice['candidate']}")
    if choice["candidate"]:
        print("rule 3:")
        for s, k in by_season[choice["candidate"]].items():
            print(_line(s, k, None))
    print(f"proceed to held-out: {choice['proceed']}")
    DEV_OUT.parent.mkdir(parents=True, exist_ok=True)
    DEV_OUT.write_text(json.dumps({"c": c, "choice": choice, "keeper": keeper, "spearman": spear,
                                   "by_season": by_season}, indent=2))
    print(f"\nwrote {DEV_OUT}")


def held_out() -> None:
    if HELD_OUT_OUT.exists():
        raise SystemExit(f"{HELD_OUT_OUT} exists, so this test has been run. See the rule in "
                         "fpledge/eval/keeper_saves.py: a rerun needs a new pre-registration.")
    if not DEV_OUT.exists():
        raise SystemExit("run the development seasons first")
    dev = json.loads(DEV_OUT.read_text())
    choice, c = dev["choice"], dev["c"]
    if not choice["proceed"]:
        raise SystemExit(f"{choice['candidate']} did not pass the development rule. Production stays.")
    candidate = choice["candidate"]
    per_goal, mode = ks.VARIANTS[candidate]
    specs = {"production": ks.VARIANTS["production"], candidate: (per_goal or c, mode)}

    rho, gk, _ = _score([cpr.load_season(*HELD_OUT)], specs, use_prior=False)
    keeper = ks.compare_keepers(gk["production"], gk[candidate])
    spear = pr.compare(rho["production"], rho[candidate])
    decision = ks.verdict(keeper, spear)

    # 2026-27: descriptive only (the rule says why)
    rho27, gk27, _ = _score([cpr.load_this_season()], specs, use_prior=True)
    keeper27 = ks.compare_keepers(gk27["production"], gk27[candidate])
    spear27 = pr.compare(rho27["production"], rho27[candidate])

    HELD_OUT_OUT.write_text(json.dumps({
        "candidate": candidate, "c": c, "keeper": keeper, "spearman": spear, "verdict": decision,
        "descriptive_2026_27": {"keeper": keeper27, "spearman": spear27}}, indent=2))
    print(f"\n{candidate} (c = {c}) against production, 2022-23:")
    print(_line("2022-23", keeper, spear))
    print(f"\nVERDICT: {decision}")
    print("\n2026-27 GW2+, descriptive only:")
    print(_line("2026-27", keeper27, spear27))
    print(f"wrote {HELD_OUT_OUT}")


if __name__ == "__main__":
    if "--held-out" in sys.argv[1:]:
        held_out()
    else:
        development()
