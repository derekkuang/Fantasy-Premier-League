#!/usr/bin/env python3
"""Can anything close the returns gap? A second attempt at a learned model, posed differently.

The first learned model (2026-07-27, `train_points_model.py`) predicted a player's total points
and lost badly to the structured model. This asks a different question, because §14's diagnostic
changed what the question should be:

    Our minutes model is BETTER than FPL's at predicting who plays (0.744 vs 0.710).
    Our returns model is much worse at ranking those who do (0.229 vs 0.516 among 85+ minutes).

So predicting total points was the wrong target — it bundles a problem we have already solved
with the one we haven't, and the solved half flatters everything. This trains only on players
who FEATURED, and asks solely: given that they played, who returns?

It also uses columns the model has never touched. `threat`, `creativity`, `influence` and
`ict_index` are FPL's own aggregations of shot volume, chance creation and involvement; `bps` is
the raw bonus-point score; `saves` is the actual save volume our goalkeeper model currently
approximates from expected goals conceded. If FPL's projection is good partly because it is
built on these, we have been ignoring the obvious.

POINT-IN-TIME, enforced the same way as the main harness: every feature for gameweek N is a
rolling per-90 built from gameweeks strictly before N, and the train/test split is by time, so
the test half is always the future relative to what the model was fitted on.

Usage: python scripts/returns_model.py [season]
"""

from __future__ import annotations

import csv
import io
import math
import pathlib
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpledge import config

SEASON = sys.argv[1] if len(sys.argv) > 1 else "2024-25"
URL = f"https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data/{SEASON}/gws/merged_gw.csv"
RECORDS = config.DATA_DIR / "eval" / f"records_{SEASON}.json"
BURN_IN = 8
MIN_GROUP = 10

# Per-90 rates rolled forward from prior gameweeks. `saves` is in here because the goalkeeper
# ranking is the worst subgroup in the whole model (§14) and the current save term is derived
# from opponent expected goals rather than from any observed save volume.
RATE_COLS = [
    "threat", "creativity", "influence", "ict_index", "bps", "saves",
    "expected_goals", "expected_assists", "expected_goals_conceded",
    "goals_scored", "assists", "clean_sheets", "bonus", "total_points",
]


def _f(x: object) -> float:
    try:
        return float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def load_rows() -> list[dict]:
    import requests

    print(f"downloading {SEASON}...")
    text = requests.get(URL, timeout=180).text
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        gw = r.get("GW") or r.get("round")
        out.append({
            "gw": int(_f(gw)), "element": int(_f(r.get("element"))),
            "pos": (r.get("position") or "").upper().replace("GKP", "GK").replace("AM", "MID"),
            "minutes": _f(r.get("minutes")), "points": _f(r.get("total_points")),
            "fpl_xp": _f(r.get("xP")),
            **{c: _f(r.get(c)) for c in RATE_COLS},
        })
    return out


def build(rows: list[dict], our_xp: dict) -> list[dict]:
    """One row per scored player-gameweek: point-in-time features + the two targets."""
    by_gw: dict = defaultdict(list)
    for r in rows:
        by_gw[r["gw"]].append(r)

    acc: dict = defaultdict(lambda: {"minutes": 0.0, "games": 0, **{c: 0.0 for c in RATE_COLS}})
    out: list[dict] = []

    for gw in sorted(by_gw):
        if gw > BURN_IN:
            for r in by_gw[gw]:
                if r["minutes"] <= 0:      # returns model: only players who featured
                    continue
                a = acc.get(r["element"])
                if not a or a["minutes"] < 180:   # too little history to rate
                    continue
                per90 = {c: a[c] / (a["minutes"] / 90.0) for c in RATE_COLS}
                out.append({
                    "gw": gw, "element": r["element"], "pos": r["pos"],
                    "y": r["points"], "fpl_xp": r["fpl_xp"],
                    "our_xp": our_xp.get((gw, r["element"]), 0.0),
                    "mins_avg": a["minutes"] / max(a["games"], 1),
                    **{f"r_{c}": v for c, v in per90.items()},
                })
        for r in by_gw[gw]:                # accumulate AFTER scoring — point-in-time
            a = acc[r["element"]]
            a["minutes"] += r["minutes"]
            a["games"] += 1
            for c in RATE_COLS:
                a[c] += r[c]
    return out


def spearman_by_gw(rows: list[dict], key) -> float:
    import scipy.stats as st

    per: dict = defaultdict(list)
    for r in rows:
        per[r["gw"]].append(r)
    out = []
    for g in per.values():
        if len(g) < MIN_GROUP:
            continue
        p = [key(r) for r in g]
        a = [r["y"] for r in g]
        if len(set(p)) < 2 or len(set(a)) < 2:
            continue
        rho = st.spearmanr(p, a).correlation
        if not math.isnan(rho):
            out.append(rho)
    return statistics.mean(out) if out else float("nan")


def main() -> None:
    import json

    import lightgbm as lgb
    import numpy as np

    our_xp: dict = {}
    if RECORDS.exists():
        for rec in json.loads(RECORDS.read_text()):
            our_xp[(rec[0], rec[1])] = rec[2]
        print(f"loaded {len(our_xp)} of our own projections from the cached walk-forward")
    else:
        print("no cached records — run scripts/model_search.py first to include our xP as a feature")

    data = build(load_rows(), our_xp)
    gws = sorted({r["gw"] for r in data})
    cut = gws[len(gws) // 2]
    train = [r for r in data if r["gw"] < cut]
    test = [r for r in data if r["gw"] >= cut]
    print(f"{len(data)} played rows | train GW{gws[0]}-{cut - 1} ({len(train)})"
          f" | test GW{cut}-{gws[-1]} ({len(test)})")

    feats = [k for k in data[0] if k.startswith("r_")] + ["mins_avg", "our_xp"]
    pos_ix = {"GK": 0, "DEF": 1, "MID": 2, "FWD": 3}

    def matrix(rows: list[dict], with_fpl: bool) -> np.ndarray:
        cols = [[r[f] for f in feats] for r in rows]
        for row, r in zip(cols, rows, strict=True):
            row.append(pos_ix.get(r["pos"], 2))
            if with_fpl:
                row.append(r["fpl_xp"])
        return np.array(cols, dtype=float)

    results: list[tuple[str, float, str]] = []
    results.append(("ours (structured xP)", spearman_by_gw(test, lambda r: r["our_xp"]), "the shipped model"))
    results.append(("FPL xP", spearman_by_gw(test, lambda r: r["fpl_xp"]), "the benchmark"))
    # A single ignored column, on its own, as a sanity floor.
    results.append(("FPL `threat` per 90 alone", spearman_by_gw(test, lambda r: r["r_threat"]),
                    "one unused column, no model"))
    results.append(("recent points per 90 alone", spearman_by_gw(test, lambda r: r["r_total_points"]),
                    "pure form, no model"))

    # LightGBM's native API — the sklearn wrapper needs scikit-learn, which this project
    # deliberately does not depend on (the numeric core is stdlib-only by design).
    y_tr = np.array([r["y"] for r in train])
    params = {
        "objective": "regression", "learning_rate": 0.05, "num_leaves": 31,
        "min_data_in_leaf": 40, "bagging_fraction": 0.8, "bagging_freq": 1,
        "feature_fraction": 0.8, "verbose": -1, "seed": 0,
    }
    top = ""
    for label, with_fpl in (("LGBM on unused columns", False), ("LGBM + FPL xP as a feature", True)):
        names = [*feats, "pos"] + (["fpl_xp"] if with_fpl else [])
        ds = lgb.Dataset(matrix(train, with_fpl), label=y_tr, feature_name=names)
        booster = lgb.train(params, ds, num_boost_round=400)
        pred = booster.predict(matrix(test, with_fpl))
        for r, p in zip(test, pred, strict=True):
            r["_p"] = float(p)
        results.append((label, spearman_by_gw(test, lambda r: r["_p"]),
                        "learned, point-in-time features"))
        if not with_fpl:
            imp = sorted(zip(names, booster.feature_importance("gain"), strict=True),
                         key=lambda t: -t[1])[:8]
            top = ", ".join(n for n, _ in imp)

    print("\n" + "=" * 78)
    print(f"RETURNS MODEL — per-GW Spearman among players who FEATURED, {SEASON} test half")
    print("=" * 78)
    fpl = next(v for n, v, _ in results if n == "FPL xP")
    for name, val, note in results:
        mark = "   <<< BEATS FPL" if val > fpl and name != "FPL xP" else ""
        print(f"  {name:<32}{val:>7.3f}   {note}{mark}")
    print(f"\n  most-used features: {top}")
    print("=" * 78)


if __name__ == "__main__":
    main()
