#!/usr/bin/env python3
"""Cards and forwards' assists: the method and the rule are in `fpledge/eval/cards_assists.py`.

Usage: python scripts/compare_cards_assists.py              development seasons, every variant
       python scripts/compare_cards_assists.py --held-out   2022-23, the chosen candidate; once only
       add --retest to either: the 2026-11-16 retest, scored on players expected to play

Offline apart from public data fetches. Changes nothing in production.
"""

from __future__ import annotations

import json
import math
import pathlib
import sys
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import compare_player_rates as cpr

from fpledge import config
from fpledge.eval import cards_assists as ca
from fpledge.eval import player_rates as pr
from fpledge.eval.fpl_backtest import validate_xp

DEV = cpr.DEV
HELD_OUT = ("2022-23", "2021-22", "2223")
RETEST = "--retest" in sys.argv[1:]
_STEM = "cards_assists_retest" if RETEST else "cards_assists"
DEV_OUT = config.DATA_DIR / "eval" / f"{_STEM}_dev.json"
HELD_OUT_OUT = config.DATA_DIR / "eval" / f"{_STEM}_held_out.json"
SCORE = "expected" if RETEST else "played"   # which rows the squared error is scored on


def _name(k: float) -> str:
    return "cards k=inf" if math.isinf(k) else f"cards k={k:g}"


def _run(job: tuple[dict, str, dict, bool]) -> tuple[str, str, dict, dict, list]:
    data, variant, spec, use_prior = job
    pairs: list = []
    p_play: dict = {}

    def sink(gw, el, row, bd):
        pairs.append((row["position"], bd["x_assists"], row.get("assists", 0)))
        p_play[(gw, el)] = max(p_play.get((gw, el), 0.0), bd["p_play"])

    _m, records = validate_xp(
        data["rows"], data["fixtures"], data["teams"], burn_in=pr.BURN_IN, minutes_mode="recent",
        fixture_lambdas=data["lambdas"],
        prior_rates=data["priors"]["position"] if use_prior else None,
        prior_k=3 if use_prior else None,
        saves_per_goal=config.SAVES_PER_EXPECTED_GOAL, dc_mode="by_case", dc_size=config.DC_NB_SIZE,
        card_prior=ca.card_prior(data["previous"]), breakdown_sink=sink, return_records=True, **spec)
    season = data["season"]
    expected = {k for k, p in p_play.items() if p >= ca.EXPECTED_TO_PLAY}
    mse = {"played": ca.mse_by_gw(records, season),
           "expected": ca.mse_by_gw(records, season, include=expected)}
    return season, variant, pr.gw_scores(records, season), mse, pairs


def _score(datasets: list[dict], specs: dict, use_prior: bool) -> tuple[dict, dict, list]:
    rho: dict = {v: {} for v in specs}
    mse: dict = {v: {} for v in specs}
    other: dict = {v: {} for v in specs}     # the score this run does not decide on, for reporting
    pairs: list = []
    jobs = [(d, v, s, use_prior) for d in datasets for v, s in specs.items()]
    with ProcessPoolExecutor(max_workers=6) as pool:
        for _season, v, r, m, p in pool.map(_run, jobs):
            rho[v].update(r)
            mse[v].update(m[SCORE])
            other[v].update(m["played" if SCORE == "expected" else "expected"])
            if v == "production":
                pairs.extend(p)
    _score.other = other
    return rho, mse, pairs


def _line(label: str, m: dict, r: dict | None) -> str:
    bias = " ".join(f"{p} {m['bias_a'][p]:+.3f}->{m['bias_b'][p]:+.3f}" for p in m["bias_b"])
    out = (f"  {label:<16} MSE {m['mse_a']:.4f} -> {m['mse_b']:.4f}  diff {m['diff']:+.4f} "
           f"[{m['ci'][0]:+.4f}, {m['ci'][1]:+.4f}]")
    if r:
        out += f"  | all ρ diff {r['diff']:+.4f} [{r['ci'][0]:+.4f}, {r['ci'][1]:+.4f}]"
    return out + f"\n{'':<19}bias (actual - xP, played): {bias}"


def _split(s: dict, season: str) -> dict:
    return {k: v for k, v in s.items() if k[0] == season}


def development() -> None:
    datasets = [cpr.load_season(*s) for s in DEV]
    specs = {"production": {}} | {_name(k): {"card_k": k} for k in ca.CARD_K_GRID}
    rho, mse, pairs = _score(datasets, specs, use_prior=True)
    _first_other = dict(_score.other)
    factors = ca.assist_factors(pairs)
    for d in datasets:
        print(f"  card prior from {d['season']}'s previous season: "
              + ", ".join(f"{p} {y:.3f}/{r:.4f}" for p, (y, r) in ca.card_prior(d["previous"]).items()))
    print(f"\nrule 2: assist factors {factors}")
    pooled = {_name(k): ca.compare_mse(mse["production"], mse[_name(k)]) for k in ca.CARD_K_GRID}
    k_best = min(ca.CARD_K_GRID, key=lambda k: pooled[_name(k)]["mse_b"])
    print("rule 3: card k by pooled MSE: " + ", ".join(f"{_name(k)} {pooled[_name(k)]['mse_b']:.4f}"
                                                     for k in ca.CARD_K_GRID) + f" -> {_name(k_best)}")
    more = {"assists": {"assist_scale": factors},
            "cards + assists": {"card_k": k_best, "assist_scale": factors}}
    rho2, mse2, _ = _score(datasets, more, use_prior=True)
    rho |= rho2
    mse |= mse2
    candidates = [_name(k_best), "assists", "cards + assists"]
    comp_m = {v: ca.compare_mse(mse["production"], mse[v]) for v in candidates}
    comp_r = {v: pr.compare(rho["production"], rho[v]) for v in candidates}
    by_season = {v: {s: ca.compare_mse(_split(mse["production"], s), _split(mse[v], s)) for s, _p, _f in DEV}
                 for v in candidates}
    other = {**_first_other, **_score.other}
    print(f"\neach candidate against production, development seasons pooled (scored on {SCORE} rows):")
    for v in candidates:
        print(_line(v, comp_m[v], comp_r[v]))
        o = ca.compare_mse(other["production"], other[v])
        print(f"{'':<19}({'played' if SCORE == 'expected' else 'expected'}-row MSE diff {o['diff']:+.4f} "
              f"[{o['ci'][0]:+.4f}, {o['ci'][1]:+.4f}], reported only)")
    choice = ca.choose(comp_m, comp_r, by_season)
    print(f"\nrule 4: eligible {choice['eligible']}, candidate {choice['candidate']}")
    if choice["candidate"]:
        for s, m in by_season[choice["candidate"]].items():
            print(_line(s, m, None))
    print(f"proceed to held-out: {choice['proceed']}")
    spec = {_name(k_best): {"card_k": k_best}} | more
    DEV_OUT.parent.mkdir(parents=True, exist_ok=True)
    DEV_OUT.write_text(json.dumps({
        "assist_factors": factors, "card_k": None if math.isinf(k_best) else k_best,
        "choice": choice, "spec": {v: {**s, "card_k": (None if math.isinf(s["card_k"]) else s["card_k"])}
                                   if "card_k" in s else s for v, s in spec.items()},
        "card_k_inf": math.isinf(k_best), "mse": comp_m, "spearman": comp_r, "by_season": by_season,
    }, indent=2))
    print(f"\nwrote {DEV_OUT}")


def held_out() -> None:
    if HELD_OUT_OUT.exists():
        raise SystemExit(f"{HELD_OUT_OUT} exists, so this test has been run. See the rule in "
                         "fpledge/eval/cards_assists.py: a rerun needs a new pre-registration.")
    if not DEV_OUT.exists():
        raise SystemExit("run the development seasons first")
    dev = json.loads(DEV_OUT.read_text())
    choice = dev["choice"]
    if not choice["proceed"]:
        raise SystemExit(f"{choice['candidate']} did not pass the development rule. Production stays.")
    candidate = choice["candidate"]
    spec = dict(dev["spec"][candidate])
    if "card_k" in spec and spec["card_k"] is None:
        spec["card_k"] = float("inf")
    specs = {"production": {}, candidate: spec}

    rho, mse, _ = _score([cpr.load_season(*HELD_OUT)], specs, use_prior=False)
    other = _score.other
    m = ca.compare_mse(mse["production"], mse[candidate])
    o = ca.compare_mse(other["production"], other[candidate])
    r = pr.compare(rho["production"], rho[candidate])
    decision = ca.verdict(m, r)

    rho27, mse27, _ = _score([cpr.load_this_season()], specs, use_prior=True)
    m27 = ca.compare_mse(mse27["production"], mse27[candidate])
    r27 = pr.compare(rho27["production"], rho27[candidate])
    HELD_OUT_OUT.write_text(json.dumps({"candidate": candidate, "spec": dev["spec"][candidate],
                                        "mse": m, "spearman": r, "verdict": decision,
                                        "descriptive_2026_27": {"mse": m27, "spearman": r27}}, indent=2))
    print(f"\n{candidate} against production, 2022-23 (scored on {SCORE} rows):")
    print(_line("2022-23", m, r))
    print(f"{'':<19}(other-row MSE diff {o['diff']:+.4f} [{o['ci'][0]:+.4f}, {o['ci'][1]:+.4f}], reported only)")
    print(f"\nVERDICT: {decision}\n\n2026-27 GW2+, descriptive only:")
    print(_line("2026-27", m27, r27))
    print(f"wrote {HELD_OUT_OUT}")


if __name__ == "__main__":
    if "--held-out" in sys.argv[1:]:
        held_out()
    else:
        development()
