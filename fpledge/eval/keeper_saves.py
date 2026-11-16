"""Keeper save points: the constant and the rounding (HANDOFF §41).

WHAT PRODUCTION DOES. A keeper's expected saves are 3 per goal the opponent is expected to score,
`x_saves = 3 x opponent lambda x (x_minutes / 90)`, and his save points are `x_saves / 3`. Two
things are wrong with that, both found on 2026-11-14 through Roefs (Sunderland), who scored 33
points over GW1-10 against about 42 projected, the whole gap in saves:

  the constant  3.0 was never measured. Keepers make about 2 saves per expected goal conceded.
  the rounding  FPL pays 1 point per 3 saves IN A MATCH, rounded down, so a two-save game earns
                nothing. x_saves / 3 pays two thirds of a point for it.

THE VARIANTS, everything else held fixed (k=3 rate blend, closing-odds lambdas, recent minutes):

  production    3.0 per expected goal, linear points
  floor         3.0 per expected goal, points with the rounding (`xpoints.expected_save_points`)
  rate          c per expected goal, linear points
  rate+floor    c per expected goal, points with the rounding

Scored per gameweek from GW2: keeper MAE over keepers who played (the term only touches keepers),
and Spearman over everyone who played, since keepers rank against outfielders in every list and
in the optimiser's budget. Keeper-only Spearman is reported, never decisive: §18 found
single-gameweek keeper ranking near noise for every model, FPL's included.

THE DECISION, WRITTEN BEFORE ANY RUN (2026-11-14).

  Development, 2023-24 to 2025-26. Production's analogue, as in `eval.player_rates`.
    1. c = total saves / total (opponent lambda x minutes / 90) over keeper fixtures with minutes,
       pooled over the development seasons, rounded to 2 decimals. A measured constant, not a
       tuned one.
    2. Of floor, rate and rate+floor, the candidate is the one with the lowest pooled keeper MAE
       among those whose all-player Spearman change against production has a 95% lower bound
       above -0.002. If none qualifies, stop: production stays.
    3. The candidate goes to the held-out test only if its keeper MAE is below production's in
       every development season, as point estimates. Otherwise stop.

  Held out, 2022-23, run once (`compare_keeper_saves.py --held-out`). No saves analysis has used
  it. 2021-22 has no FPL xG, so both arms use this season's rates only (no prior); that is the
  same for both and does not touch the keeper term.
    SHIP           keeper MAE lower with a 95% interval below zero, and the all-player Spearman
                   change has a 95% lower bound above -0.002.
    DO NOT SHIP    keeper MAE higher with a 95% interval above zero, or the Spearman change has
                   a 95% upper bound below zero.
    INCONCLUSIVE   anything else. Production stays.

  2026-27 GW2-10 is reported beside it and decides nothing. Before this rule was written I had
  looked at this season's keeper totals (1.94 saves per expected goal conceded; 0.62 save points
  per full game against the formula's 1.47), so it cannot be a clean test.

Intervals are a bootstrap over whole gameweeks, as in `eval.player_rates`.
"""

from __future__ import annotations

import random
import statistics
from collections import defaultdict
from collections.abc import Iterable, Sequence

N_BOOT = 2000
SPEARMAN_MARGIN = -0.002
VARIANTS = {             # name: (saves per expected goal, None = the measured c; points mode)
    "production": (3.0, "linear"),
    "floor": (3.0, "floor"),
    "rate": (None, "linear"),
    "rate+floor": (None, "floor"),
}


def fit_saves_per_goal(pairs: Iterable[tuple[int, int, float]]) -> float:
    """c from (saves, minutes, opponent lambda) per keeper fixture, over fixtures he played."""
    saves = expected = 0.0
    for s, minutes, opp_lambda in pairs:
        if minutes > 0:
            saves += s
            expected += opp_lambda * minutes / 90.0
    if expected <= 0:
        raise ValueError("no keeper minutes to fit on")
    return round(saves / expected, 2)


def keeper_errors(records: Sequence[tuple], season: str) -> dict:
    """{(season, gw): {"abs_err", "err", "n", "keys"}} over keepers who played."""
    out: dict = defaultdict(lambda: {"abs_err": 0.0, "err": 0.0, "n": 0, "keys": set()})
    for gw, element, xp, _fpl, actual, pos, minutes in records:
        if pos == "GK" and minutes > 0:
            g = out[(season, gw)]
            g["abs_err"] += abs(xp - actual)
            g["err"] += actual - xp
            g["n"] += 1
            g["keys"].add(element)
    return {k: {**v, "keys": frozenset(v["keys"])} for k, v in out.items()}


def compare_keepers(a: dict, b: dict, n_boot: int = N_BOOT, seed: int = 0) -> dict | None:
    """B against A on keeper MAE. A negative `diff` means B is more accurate."""
    keys = sorted(set(a) & set(b))
    for k in keys:
        if a[k]["keys"] != b[k]["keys"]:
            raise ValueError(f"{k}: the two variants scored different keepers")
    if not keys:
        return None
    diffs = [(b[k]["abs_err"] - a[k]["abs_err"]) / a[k]["n"] for k in keys]
    rng = random.Random(seed)
    boot = sorted(statistics.fmean(rng.choices(diffs, k=len(diffs))) for _ in range(n_boot))
    n = sum(a[k]["n"] for k in keys)
    return {
        "n_gws": len(keys), "n_rows": n,
        "mae_a": sum(a[k]["abs_err"] for k in keys) / n,
        "mae_b": sum(b[k]["abs_err"] for k in keys) / n,
        "bias_a": sum(a[k]["err"] for k in keys) / n,   # actual - xP: negative = projected too high
        "bias_b": sum(b[k]["err"] for k in keys) / n,
        "diff": statistics.fmean(diffs),
        "ci": [boot[int(0.025 * n_boot)], boot[min(n_boot - 1, int(0.975 * n_boot))]],
    }


def choose(keeper: dict, spearman: dict, by_season: dict) -> dict:
    """Rules 2 and 3. `keeper` and `spearman` are {variant: comparison against production},
    pooled; `by_season` is {variant: {season: keeper comparison}}."""
    eligible = [v for v in ("floor", "rate", "rate+floor") if spearman[v]["ci"][0] > SPEARMAN_MARGIN]
    if not eligible:
        return {"candidate": None, "eligible": [], "proceed": False}
    candidate = min(eligible, key=lambda v: keeper[v]["mae_b"])
    every = all(r["mae_b"] < r["mae_a"] for r in by_season[candidate].values())
    return {"candidate": candidate, "eligible": eligible, "proceed": every}


def verdict(keeper: dict, spearman: dict) -> str:
    if keeper["ci"][0] > 0 or spearman["ci"][1] < 0:
        return "DO NOT SHIP"
    if keeper["ci"][1] < 0 and spearman["ci"][0] > SPEARMAN_MARGIN:
        return "SHIP"
    return "INCONCLUSIVE"
