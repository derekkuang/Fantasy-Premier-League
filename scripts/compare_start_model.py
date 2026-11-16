#!/usr/bin/env python3
"""Minutes from a start-probability model: the method and the rule are in `fpledge/eval/start_model.py`.

Usage: python scripts/compare_start_model.py              development (2025-26), then the refit
       python scripts/compare_start_model.py --held-out   2026-27 with the refit; once only

Offline apart from public data fetches. Changes nothing in production until the refit is
wired in by hand.
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
from fpledge.eval import start_model as sm
from fpledge.eval.fpl_backtest import validate_xp
from fpledge.ingest import vaastav
from fpledge.models import starts

TRAIN = ["2023-24", "2024-25"]
DEV = ("2025-26", "2024-25", "2526")
DEV_OUT = config.DATA_DIR / "eval" / "start_model_dev.json"
HELD_OUT_OUT = config.DATA_DIR / "eval" / "start_model_held_out.json"


def _rows(season: str) -> list:
    return starts.training_rows(sm.season_histories(vaastav.fetch_player_gws(season)))


def _run(job: tuple[dict, str, dict | None]) -> tuple[str, dict, dict, dict, dict]:
    data, variant, model_json = job
    p_play: dict = {}
    appeared: dict = {}

    def sink(gw, el, row, bd):
        p_play[(gw, el)] = max(p_play.get((gw, el), 0.0), bd["p_play"])
        appeared[(gw, el)] = max(appeared.get((gw, el), 0), int(row["minutes"] > 0))

    model = starts.StartModel.from_json(model_json) if model_json else None
    _m, records = validate_xp(
        data["rows"], data["fixtures"], data["teams"], burn_in=pr.BURN_IN,
        minutes_mode="starts" if model else "recent", start_model=model,
        fixture_lambdas=data["lambdas"], prior_rates=data["priors"]["position"], prior_k=3,
        saves_per_goal=config.SAVES_PER_EXPECTED_GOAL, dc_mode="by_case", dc_size=config.DC_NB_SIZE,
        card_k=float("inf"), card_prior=ca.card_prior(data["previous"]),
        assist_scale=config.ASSIST_SCALE, breakdown_sink=sink, return_records=True)
    return variant, pr.gw_scores(records, data["season"]), records, p_play, appeared


def _compare(data: dict, model: starts.StartModel) -> dict:
    jobs = [(data, "production", None), (data, "start model", model.to_json())]
    with ProcessPoolExecutor(max_workers=2) as pool:
        out = {v: (rho, recs, pp, ap) for v, rho, recs, pp, ap in pool.map(_run, jobs)}
    include = sm.expected_rows(out["production"][2], out["start model"][2])
    season = data["season"]
    mse = {v: ca.mse_by_gw(out[v][1], season, include=include) for v in out}
    return {
        "mse": ca.compare_mse(mse["production"], mse["start model"]),
        "spearman": pr.compare(out["production"][0], out["start model"][0]),
        "plays_brier": {v: sm.plays_brier(out[v][2], out[v][3]) for v in out},
        "rows": len(include),
    }


def _report(label: str, r: dict) -> None:
    m, s = r["mse"], r["spearman"]
    print(f"  {label}: squared error {m['mse_a']:.4f} -> {m['mse_b']:.4f}  diff {m['diff']:+.4f} "
          f"[{m['ci'][0]:+.4f}, {m['ci'][1]:+.4f}]  ({r['rows']} expected-to-play rows)")
    print(f"  {'':<{len(label)}}  ranking ρ {s['rho_a']:.4f} -> {s['rho_b']:.4f}  diff {s['diff']:+.4f} "
          f"[{s['ci'][0]:+.4f}, {s['ci'][1]:+.4f}]")
    print(f"  {'':<{len(label)}}  plays Brier {r['plays_brier']['production']:.4f} -> "
          f"{r['plays_brier']['start model']:.4f}")
    print(f"  {'':<{len(label)}}  bias on those rows (actual - xP): "
          + " ".join(f"{p} {m['bias_a'][p]:+.2f}->{m['bias_b'][p]:+.2f}" for p in m["bias_b"]))


def development() -> None:
    import numpy as np
    from sklearn.metrics import log_loss

    train = [r for s in TRAIN for r in _rows(s)]
    dev_rows = _rows(DEV[0])
    X = [r[0] for r in dev_rows]
    y = [r[1] for r in dev_rows]
    losses, fits = {}, {}
    for c in sm.C_GRID:
        fits[c] = starts.fit(train, TRAIN, c=c)
        p = [starts._sigmoid(fits[c]._lin(fits[c].start, x)) for x in X]
        losses[c] = log_loss(y, np.clip(p, 1e-6, 1 - 1e-6))
    c = min(sm.C_GRID, key=losses.get)
    print("rule 1: P(start) log-loss on 2025-26 by C: "
          + ", ".join(f"{k:g} {v:.4f}" for k, v in losses.items()) + f" -> C = {c:g}")

    r = _compare(cpr.load_season(*DEV), fits[c])
    print("\nrule 2: start model (fit on 2023-25) against production, 2025-26:")
    _report("2025-26", r)
    proceed = r["mse"]["ci"][1] < 0 and r["spearman"]["ci"][0] > ca.SPEARMAN_MARGIN
    print(f"proceed: {proceed}")
    out = {"c": c, "log_loss": losses, "dev": r, "proceed": proceed}
    if proceed:
        refit = starts.fit(train + dev_rows, TRAIN + [DEV[0]], c=c)
        starts.MODEL_PATH.write_text(json.dumps(refit.to_json(), indent=1) + "\n")
        print(f"rule 3: refit on {refit.trained_on}, wrote {starts.MODEL_PATH}")
    DEV_OUT.parent.mkdir(parents=True, exist_ok=True)
    DEV_OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"wrote {DEV_OUT}")


def held_out() -> None:
    if HELD_OUT_OUT.exists():
        raise SystemExit(f"{HELD_OUT_OUT} exists, so this test has been run. See the rule in "
                         "fpledge/eval/start_model.py: a rerun needs a new pre-registration.")
    if not DEV_OUT.exists() or not json.loads(DEV_OUT.read_text())["proceed"]:
        raise SystemExit("development did not pass (or has not run). Production stays.")
    model = starts.load()
    r = _compare(cpr.load_this_season(), model)
    decision = ca.verdict(r["mse"], r["spearman"])
    HELD_OUT_OUT.write_text(json.dumps({**r, "trained_on": model.trained_on, "c": model.c,
                                        "verdict": decision}, indent=2, default=str))
    print(f"\nstart model (fit on {model.trained_on}) against production, 2026-27:")
    _report("2026-27", r)
    print(f"\nVERDICT: {decision}\nwrote {HELD_OUT_OUT}")


if __name__ == "__main__":
    if "--held-out" in sys.argv[1:]:
        held_out()
    else:
        development()
