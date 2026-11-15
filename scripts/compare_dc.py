#!/usr/bin/env python3
"""Defensive contribution: the method and the rule are in `fpledge/eval/defensive_contribution.py`.

Usage: python scripts/compare_dc.py              2025-26, every variant
       python scripts/compare_dc.py --held-out   2026-27, the chosen candidate; once only

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
from fpledge.eval import defensive_contribution as dc
from fpledge.eval import player_rates as pr
from fpledge.eval.fpl_backtest import validate_xp

DEV = ("2025-26", "2024-25", "2526")
DEV_OUT = config.DATA_DIR / "eval" / "dc_dev.json"
HELD_OUT_OUT = config.DATA_DIR / "eval" / "dc_held_out.json"


def _spec(variant: str, sizes: dict) -> dict:
    if variant == "production":
        return {"dc_mode": "expected"}
    if variant == "by case":
        return {"dc_mode": "by_case"}
    return {"dc_mode": "by_case", "dc_size": sizes}


def _run(job: tuple[dict, str, dict]) -> tuple[str, dict, dict, dict]:
    data, variant, spec = job
    cases: list = []

    def sink(gw, el, row, bd):
        pos = row["position"]
        if pos in dc.POSITIONS:
            cases.append((gw, el, row["opponent_team"], pos, bd["p_dc_point"],
                          int(row["dc"] >= dc.threshold(pos))))

    _m, records = validate_xp(
        data["rows"], data["fixtures"], data["teams"], burn_in=pr.BURN_IN, minutes_mode="recent",
        fixture_lambdas=data["lambdas"], prior_rates=data["priors"]["position"], prior_k=3,
        saves_per_goal=config.SAVES_PER_EXPECTED_GOAL, breakdown_sink=sink, return_records=True,
        **spec)
    season = data["season"]
    mae = {}
    for gw, _el, xp, _f, actual, pos, minutes in records:
        if pos in dc.POSITIONS and minutes > 0:
            m = mae.setdefault(pos, [0.0, 0])
            m[0] += abs(xp - actual)
            m[1] += 1
    return variant, pr.gw_scores(records, season), dc.brier_by_gw(cases, season), mae


def _score(data: dict, specs: dict) -> tuple[dict, dict, dict]:
    rho, brier, mae = {}, {}, {}
    with ProcessPoolExecutor(max_workers=3) as pool:
        for variant, r, b, m in pool.map(_run, [(data, v, s) for v, s in specs.items()]):
            rho[variant], brier[variant], mae[variant] = r, b, m
    return rho, brier, mae


def _line(label: str, b: dict, r: dict | None) -> str:
    cal = "  ".join(f"{p} DC pts {b['calibration_a'][p]['expected']:.3f}->{b['calibration_b'][p]['expected']:.3f}"
                    f" (actual {b['calibration_b'][p]['actual']:.3f})" for p in dc.POSITIONS)
    out = (f"  {label:<13} Brier {b['brier_a']:.4f} -> {b['brier_b']:.4f}  diff {b['diff']:+.4f} "
           f"[{b['ci'][0]:+.4f}, {b['ci'][1]:+.4f}]")
    if r:
        out += f"  | all ρ {r['rho_a']:.4f} -> {r['rho_b']:.4f} diff {r['diff']:+.4f} [{r['ci'][0]:+.4f}, {r['ci'][1]:+.4f}]"
    return out + "\n" + " " * 16 + cal


def _mae_line(mae: dict) -> str:
    return "  ".join(f"{v}: " + ", ".join(f"{p} {s[0] / s[1]:.3f}" for p, s in sorted(m.items()))
                     for v, m in mae.items())


def development() -> None:
    data = cpr.load_season(*DEV)
    sizes = dc.fit_sizes(data["rows"])
    print(f"\nrule 1: negative-binomial sizes {sizes}")
    specs = {v: _spec(v, sizes) for v in dc.VARIANTS}
    rho, brier, mae = _score(data, specs)
    comp_b, comp_r, halves = {}, {}, {}
    print("\neach variant against production, 2025-26:")
    for v in dc.VARIANTS[1:]:
        comp_b[v] = dc.compare_brier(brier["production"], brier[v])
        comp_r[v] = pr.compare(rho["production"], rho[v])
        halves[v] = {label: dc.compare_brier(
            {k: x for k, x in brier["production"].items() if lo <= k[1] <= hi},
            {k: x for k, x in brier[v].items() if lo <= k[1] <= hi})
            for label, lo, hi in (("GW2-19", 2, 19), ("GW20-38", 20, 38))}
        print(_line(v, comp_b[v], comp_r[v]))
    print("  DEF/MID MAE, played: " + _mae_line(mae))
    choice = dc.choose(comp_b, comp_r, halves)
    print(f"\nrule 2: eligible {choice['eligible']}, candidate {choice['candidate']}")
    if choice["candidate"]:
        print("rule 3:")
        for label, b in halves[choice["candidate"]].items():
            print(_line(label, b, None))
    print(f"proceed to held-out: {choice['proceed']}")
    DEV_OUT.parent.mkdir(parents=True, exist_ok=True)
    DEV_OUT.write_text(json.dumps({"sizes": sizes, "choice": choice, "brier": comp_b,
                                   "spearman": comp_r, "halves": halves, "mae": mae}, indent=2))
    print(f"\nwrote {DEV_OUT}")


def held_out() -> None:
    if HELD_OUT_OUT.exists():
        raise SystemExit(f"{HELD_OUT_OUT} exists, so this test has been run. See the rule in "
                         "fpledge/eval/defensive_contribution.py: a rerun needs a new pre-registration.")
    if not DEV_OUT.exists():
        raise SystemExit("run the development season first")
    dev = json.loads(DEV_OUT.read_text())
    choice, sizes = dev["choice"], dev["sizes"]
    if not choice["proceed"]:
        raise SystemExit(f"{choice['candidate']} did not pass the development rule. Production stays.")
    candidate = choice["candidate"]
    specs = {"production": _spec("production", sizes), candidate: _spec(candidate, sizes)}
    rho, brier, mae = _score(cpr.load_this_season(), specs)
    b = dc.compare_brier(brier["production"], brier[candidate])
    r = pr.compare(rho["production"], rho[candidate])
    decision = dc.verdict(b, r)
    HELD_OUT_OUT.write_text(json.dumps({"candidate": candidate, "sizes": sizes, "brier": b,
                                        "spearman": r, "mae": mae, "verdict": decision}, indent=2))
    print(f"\n{candidate} against production, 2026-27:")
    print(_line("2026-27", b, r))
    print("  DEF/MID MAE, played: " + _mae_line(mae))
    print(f"\nVERDICT: {decision}\nwrote {HELD_OUT_OUT}")


if __name__ == "__main__":
    if "--held-out" in sys.argv[1:]:
        held_out()
    else:
        development()
