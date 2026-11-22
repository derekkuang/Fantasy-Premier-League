"""Keeper save points with FPL's per-match rounding (E5 in docs/MODEL_FIXES.md).

WHAT PRODUCTION DOES. A keeper's save points are `x_saves / 3`. FPL pays 1 point per 3 saves IN A
MATCH, rounded down, so a two-save game earns nothing and a five-save game earns one. Linear
points pay two thirds of a point for the first and five thirds for the second. §41 measured the
constant (2.02 saves per expected goal conceded, E1, live) and left the rounding out because the
held-out run that chose the constant scored keepers who played, a score biased against any term
that lowers projections (§43). `xpoints.expected_save_points` already computes the rounded mean,
E[floor(S / 3)] for S ~ Poisson; the harness has it as `save_points_mode="floor"`.

WHAT WAS LOOKED AT before this rule was written (2026-11-22). The term audit on 2023-24 to
2025-26, production's analogue (start model, k=3 prior, c = 2.02, defensive contribution by case,
cards, assist scale, closing-odds lambdas), keepers the model expected to start: save points
0.906 a fixture projected, 0.611 with the rounding, 0.599 awarded; keepers' total 3.297 projected
against 2.966 scored, -0.33, the save term all of it. Per season the save term ran -0.26, -0.33
and -0.33. §44 reported keepers expected to play on 2026-27 GW2-10 at +0.10 after the start
model, all terms together. Nothing from GW12 on has been played.

THE VARIANTS, everything else at production's settings:
  production   linear save points, x_saves / 3
  floor        rounded save points, `expected_save_points(x_saves, x_minutes)`

THE ROWS. Keeper fixtures the model expected to start (p_play >= EXPECTED_TO_PLAY), whether or
not he played, so that the term is judged over the same rows it is projected for (§43). The
save term is judged against what FPL awarded for it: saves // 3 in that fixture.

THE DECISION, WRITTEN BEFORE ANY RUN (2026-11-22).

  Development, 2023-24 to 2025-26 (`scripts/compare_save_rounding.py`). Floor proceeds only if
  all three hold:
    1. Every season: floor's save-term gap (awarded - projected, per fixture) has an interval
       that reaches inside +-TOL_SAVES, and is smaller in size than production's.
    2. Pooled: keeper squared error over the same rows, floor minus production, has a 95% upper
       bound below zero.
    3. Pooled: the all-player Spearman change, over players who played as in every fix since
       §36, has a 95% lower bound above SPEARMAN_MARGIN.
  Otherwise stop: production stays.

  Confirmation, CONFIRM_SEASON CONFIRM_GWS: the first four gameweeks not played when this rule
  was committed (GW11's deadline passed on 2026-11-21 and its matches are under way). Run once,
  after GW15 is final, from our own landed results (`compare_save_rounding.py --confirm`).
    SHIP           floor's save-term interval reaches inside +-TOL_SAVES and production's does not.
    DO NOT SHIP    production's reaches inside and floor's does not.
    INCONCLUSIVE   anything else. Production stays; shipping is then the owner's call.
  Reported beside it, deciding nothing: keeper squared error and bias on the same rows, and the
  all-player Spearman change. The change moves every keeper by nearly the same amount, so its
  ranking effect does not depend on the weeks; four gameweeks cannot bound it, and development's
  111 can (rule 3).

Intervals: 95%, a bootstrap over whole gameweeks (ratio of sums), N_BOOT draws, seed SEED.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

import numpy as np

EXPECTED_TO_PLAY = 0.5
TOL_SAVES = 0.05
SPEARMAN_MARGIN = -0.002
CONFIRM_SEASON = "2026-27"
CONFIRM_GWS = (12, 15)
N_BOOT = 2000
SEED = 20261122
ARMS = ("production", "floor")


def term_sums(rows: Iterable[dict]) -> dict:
    """{(season, gw): {"awarded", "projected", "n"}} over keeper fixtures expected to start.

    Each row: season, gw, p_play, projected (this arm's save points), awarded (saves // 3)."""
    out: dict = defaultdict(lambda: {"awarded": 0.0, "projected": 0.0, "n": 0})
    for r in rows:
        if r["p_play"] >= EXPECTED_TO_PLAY:
            g = out[(r["season"], r["gw"])]
            g["awarded"] += r["awarded"]
            g["projected"] += r["projected"]
            g["n"] += 1
    return dict(out)


def term_gap(sums: dict, n_boot: int = N_BOOT, seed: int = SEED) -> dict | None:
    """Awarded minus projected save points per fixture, with a gameweek-block interval."""
    keys = sorted(sums)
    if not keys:
        return None
    a = np.array([sums[k]["awarded"] for k in keys])
    p = np.array([sums[k]["projected"] for k in keys])
    n = np.array([sums[k]["n"] for k in keys], dtype=float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(keys), size=(n_boot, len(keys)))
    boot = np.sort((a[idx].sum(1) - p[idx].sum(1)) / n[idx].sum(1))
    return {"n_gws": len(keys), "n": int(n.sum()), "awarded": float(a.sum() / n.sum()),
            "projected": float(p.sum() / n.sum()), "gap": float((a.sum() - p.sum()) / n.sum()),
            "ci": [float(boot[int(0.025 * n_boot)]), float(boot[min(n_boot - 1, int(0.975 * n_boot))])]}


def reaches(ci: list, tol: float = TOL_SAVES) -> bool:
    """The interval overlaps [-tol, +tol]."""
    return ci[0] <= tol and ci[1] >= -tol


def development(by_season: dict, mse: dict, spearman: dict) -> dict:
    """Rules 1-3. `by_season` {season: {arm: term_gap}}; `mse` and `spearman` are floor against
    production, pooled (`cards_assists.compare_mse`, `player_rates.compare`)."""
    rule1 = {s: reaches(g["floor"]["ci"]) and abs(g["floor"]["gap"]) < abs(g["production"]["gap"])
             for s, g in by_season.items()}
    rule2 = mse["ci"][1] < 0
    rule3 = spearman["ci"][0] > SPEARMAN_MARGIN
    return {"rule1": rule1, "rule2": rule2, "rule3": rule3,
            "proceed": bool(rule1) and all(rule1.values()) and rule2 and rule3}


def verdict(gaps: dict) -> str:
    """The confirmation. `gaps` {arm: term_gap} on CONFIRM_GWS."""
    floor_in, prod_in = reaches(gaps["floor"]["ci"]), reaches(gaps["production"]["ci"])
    if floor_in and not prod_in:
        return "SHIP"
    if prod_in and not floor_in:
        return "DO NOT SHIP"
    return "INCONCLUSIVE"
