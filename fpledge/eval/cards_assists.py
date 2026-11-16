"""Cards and forwards' assists (docs/MODEL_FIXES.md E3, E4; HANDOFF §43).

WHAT PRODUCTION DOES. It has no card term, though a yellow costs 1 point and a red 3: about
-0.21 points per 90 for defenders, -0.23 midfielders, -0.18 forwards, -0.08 keepers (2023-26).
And it gives each player an assist share from his xA, but FPL credits assists xA cannot see (a
won penalty, a parried shot scored from): forwards get 0.094 a game against 0.062 projected,
while defenders and midfielders run slightly below.

WHAT WAS LOOKED AT FIRST (2023-26, development, before this was written): card rates by position;
a player's yellow rate in odd against even games, r = +0.22, +0.11, +0.27 (weakly his own); assists
against projection by position; and forwards' assists minus xA in odd against even games, r =
+0.22, +0.05, +0.08 (mostly not his own, so a position factor). 2022-23 has been used only for
keeper saves; its cards and assists have not been looked at.

THE VARIANTS, everything else as production now is (k=3 rate blend, closing-odds lambdas, saves at
2.02, defensive contribution by case):

  production       no card term, assist shares from xA
  cards k          expected card points = -(yellows + 3 x reds per 90) x expected minutes / 90, each
                   rate this season's blended with last season's position rate as if worth k games;
                   k = inf is the position rate alone
  assists          each assist share x the position's factor (rule 2)
  cards + assists  both

THE DECISION, WRITTEN BEFORE ANY RUN (2026-11-14).

  Scored: mean squared error of total points over players who played, per gameweek. Both terms
  move projections up or down towards an average, and squared error is the proper score for an
  average; absolute error is not, and would punish raising a too-low projection. Guard: the
  all-player Spearman, as in every test.

  Development, 2023-24 to 2025-26.
    1. Card prior per position: last season's players with 270+ minutes, total yellows and reds
       per 90. (For 2022-23, 2021-22's.)
    2. Assist factor per position (DEF, MID, FWD; keepers 1): total FPL assists / total projected
       assists over every projected fixture of the production run, pooled over the development
       seasons, rounded to 2 decimals.
    3. Card k from (10, 20, 40, inf): the lowest pooled MSE of "cards k".
    4. Of cards k, assists and cards + assists, the candidate is the lowest pooled MSE among those
       whose Spearman change against production has a 95% lower bound above -0.002. It goes to
       the held-out test only if its MSE is below production's in every development season, as
       point estimates. Otherwise stop.

  Held out, 2022-23, run once (`compare_cards_assists.py --held-out`). 2021-22 has no FPL xG, so
  both arms use this season's rates only; the card prior is 2021-22's.
    SHIP           MSE lower with a 95% interval below zero, and the Spearman change has a 95%
                   lower bound above -0.002.
    DO NOT SHIP    MSE higher with a 95% interval above zero, or the Spearman change has a 95%
                   upper bound below zero.
    INCONCLUSIVE   anything else. Production stays.

  2026-27 GW2-10 is reported beside it and decides nothing: its keepers and defensive numbers have
  been looked at, though not its cards or assists.

Intervals are a bootstrap over whole gameweeks.

RESULT OF THE ABOVE (HANDOFF §43): stopped at development. Cards improved the ranking (+0.0012
[+0.0007, +0.0017]) but squared error on played rows got worse, and that score is biased against
any term that lowers projections: it keeps the rows where the player played, so it drops the zeros
of expected starters who did not, and every outfield position already reads 0.3 under there.

THE RETEST, WRITTEN BEFORE ITS RUN (2026-11-16), at the user's request.

  Scored: squared error of total points over every player the model EXPECTED to play, p_play >= 0.5
  in the pre-deadline projection, whether or not he then played. The rows are chosen by the
  forecast, not the result, which removes the bias; and it keeps the test on the players a manager
  would pick, which is what the user asked for.

  What had been seen before this was written: the first test's development results above, on
  2023-26, scored on played rows. Nothing on the new rows, and nothing at all on 2022-23's cards or
  assists, because the first test never reached it.

  Rules 1 and 2 unchanged (the same measurements). Rule 3: card k by the lowest pooled squared
  error on the new rows. Rule 4 and the held-out verdict exactly as above, with squared error on
  the new rows in place of played rows. Held out, 2022-23, run once
  (`compare_cards_assists.py --retest --held-out`). Reported beside it, deciding nothing:
  played-row squared error, the bias by position on the new rows, and 2026-27 GW2-10.
"""

from __future__ import annotations

import random
import statistics
from collections import defaultdict
from collections.abc import Iterable, Sequence

N_BOOT = 2000
SPEARMAN_MARGIN = -0.002
MIN_PRIOR_MINUTES = 270
CARD_K_GRID = (10.0, 20.0, 40.0, float("inf"))
EXPECTED_TO_PLAY = 0.5   # the retest's rows: p_play at or above this before the deadline


def card_prior(previous: Iterable[dict]) -> dict:
    """Rule 1. {position: (yellows per 90, reds per 90)} from last season's regulars."""
    tot: dict = defaultdict(lambda: [0.0, 0.0, 0.0])
    for p in previous:
        if p.get("position") and p["minutes"] >= MIN_PRIOR_MINUTES:
            t = tot[p["position"]]
            t[0] += p.get("yellow_cards", 0)
            t[1] += p.get("red_cards", 0)
            t[2] += p["minutes"] / 90.0
    return {pos: (y / n, r / n) for pos, (y, r, n) in tot.items() if n > 0}


def assist_factors(pairs: Iterable[tuple[str, float, int]]) -> dict:
    """Rule 2. {position: FPL assists / projected assists} from (position, x_assists, assists)."""
    exp: dict = defaultdict(float)
    act: dict = defaultdict(float)
    for pos, x, a in pairs:
        exp[pos] += x
        act[pos] += a
    return {pos: round(act[pos] / exp[pos], 2) for pos in ("DEF", "MID", "FWD") if exp[pos] > 0}


def mse_by_gw(records: Sequence[tuple], season: str, include: set | None = None) -> dict:
    """{(season, gw): {"sq", "err", "n", "keys", "by_pos"}}.

    Over players who played, or, with `include` ({(gw, element)}), over exactly those rows whether
    or not the player played: the retest's players expected to play."""
    out: dict = defaultdict(lambda: {"sq": 0.0, "err": 0.0, "n": 0, "keys": set(),
                                     "by_pos": defaultdict(lambda: [0.0, 0])})
    for gw, element, xp, _fpl, actual, pos, minutes in records:
        if (minutes > 0) if include is None else ((gw, element) in include):
            g = out[(season, gw)]
            g["sq"] += (xp - actual) ** 2
            g["err"] += actual - xp
            g["n"] += 1
            g["keys"].add(element)
            g["by_pos"][pos][0] += actual - xp
            g["by_pos"][pos][1] += 1
    return {k: {**v, "keys": frozenset(v["keys"]), "by_pos": dict(v["by_pos"])} for k, v in out.items()}


def compare_mse(a: dict, b: dict, n_boot: int = N_BOOT, seed: int = 0) -> dict | None:
    """B against A. A negative `diff` means B's projections are closer, in squared error."""
    keys = sorted(set(a) & set(b))
    for k in keys:
        if a[k]["keys"] != b[k]["keys"]:
            raise ValueError(f"{k}: the two variants scored different players")
    if not keys:
        return None
    diffs = [(b[k]["sq"] - a[k]["sq"]) / a[k]["n"] for k in keys]
    rng = random.Random(seed)
    boot = sorted(statistics.fmean(rng.choices(diffs, k=len(diffs))) for _ in range(n_boot))
    n = sum(a[k]["n"] for k in keys)

    def bias(s: dict) -> dict:   # actual - projected, per scored row, by position
        out = {}
        for pos in ("GK", "DEF", "MID", "FWD"):
            e = sum(s[k]["by_pos"].get(pos, [0.0, 0])[0] for k in keys)
            c = sum(s[k]["by_pos"].get(pos, [0.0, 0])[1] for k in keys)
            if c:
                out[pos] = e / c
        return out

    return {
        "n_gws": len(keys), "n_rows": n,
        "mse_a": sum(a[k]["sq"] for k in keys) / n, "mse_b": sum(b[k]["sq"] for k in keys) / n,
        "diff": statistics.fmean(diffs),
        "ci": [boot[int(0.025 * n_boot)], boot[min(n_boot - 1, int(0.975 * n_boot))]],
        "bias_a": bias(a), "bias_b": bias(b),
    }


def choose(mse: dict, spearman: dict, by_season: dict) -> dict:
    """Rule 4. {variant: comparison against production}; `by_season` {variant: {season: MSE comparison}}."""
    eligible = [v for v in mse if spearman[v]["ci"][0] > SPEARMAN_MARGIN]
    if not eligible:
        return {"candidate": None, "eligible": [], "proceed": False}
    candidate = min(eligible, key=lambda v: mse[v]["mse_b"])
    every = all(r["mse_b"] < r["mse_a"] for r in by_season[candidate].values())
    return {"candidate": candidate, "eligible": eligible, "proceed": every}


def verdict(mse: dict, spearman: dict) -> str:
    if mse["ci"][0] > 0 or spearman["ci"][1] < 0:
        return "DO NOT SHIP"
    if mse["ci"][1] < 0 and spearman["ci"][0] > SPEARMAN_MARGIN:
        return "SHIP"
    return "INCONCLUSIVE"
