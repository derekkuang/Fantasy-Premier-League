"""Defensive contribution: the threshold chance, case by case (HANDOFF §42, docs/MODEL_FIXES.md E2).

WHAT PRODUCTION DOES. `dc_point_probability` takes a player's defensive actions per 90 times his
EXPECTED minutes and asks how likely a Poisson count with that mean reaches the threshold (10 for
defenders, 12 for midfielders and forwards). Expected minutes already include the chance he does
not play, and the tail is steep, so a rotation player's chance is crushed: 60% to start at 9 a
full game gives 0.05 instead of about 0.22.

WHAT WAS CHECKED FIRST (2025-26, development, looked at on 2026-11-14 before this was written):
the Poisson curve is not the problem. At a known per-player mean (15+ full games) the hit rate
matches Poisson within 0.03 in every band; variance/mean is 1.38 for defenders, 1.13 for
midfielders. Also looked at: 1-59 minute appearances average 22.2 minutes, and the §41 audit's DC
calibration. 2026-27's defensive numbers have not been looked at.

THE VARIANTS, everything else held fixed (k=3 rate blend, closing-odds lambdas, recent minutes,
keeper saves as production):

  production       Poisson tail at expected minutes
  by case          plays 60+ (p_60, at the minutes that leaves) or comes on (p_play - p_60, at
                   22 minutes), Poisson tail in each, weighted
  by case, NB      the same with a negative binomial, size fitted per position (rule 1)

THE DECISION, WRITTEN BEFORE ANY RUN (2026-11-14).

  Scored: the DC Brier score, (p - hit)^2 over every defender and midfielder fixture the harness
  projects, hit = the player's defensive count reached his threshold. Brier is a proper score for
  a probability; MAE on total points is not one for a mean, and would punish raising a too-low
  projection towards the truth. Guard: all-player played-only Spearman, as in every test.

  Development, 2025-26, the only finished season with the rule. Its season before had no
  defensive stat, so every rate starts from zero and stays shrunk; that is the same for every
  variant, and is why the held-out season decides.
    1. Negative-binomial size per position by a pooled moment fit on players with 15+ full games
       (85+ minutes): defenders alone, midfielders and forwards together (same count, same
       threshold). Rounded to whole numbers.
    2. The candidate is the variant with the lower Brier among those whose Spearman change against
       production has a 95% lower bound above -0.002. If neither qualifies, stop.
    3. It goes to the held-out test only if its Brier is below production's in both halves of
       the season (GW2-19 and GW20-38), as point estimates. Otherwise stop.

  Held out, 2026-27 GW2 onwards, run once (`compare_dc.py --held-out`). Production's analogue,
  with last season's defensive rates as the prior.
    SHIP           Brier lower with a 95% interval below zero, and the Spearman change has a 95%
                   lower bound above -0.002.
    DO NOT SHIP    Brier higher with a 95% interval above zero, or the Spearman change has a 95%
                   upper bound below zero.
    INCONCLUSIVE   anything else. Production stays.

  Reported, deciding nothing: expected against actual DC points per game for defenders and
  midfielders, and defender/midfielder MAE on total points.

Intervals are a bootstrap over whole gameweeks.
"""

from __future__ import annotations

import random
import statistics
from collections import defaultdict
from collections.abc import Iterable

from .. import config

N_BOOT = 2000
SPEARMAN_MARGIN = -0.002
FULL_GAME = 85
MIN_FULL_GAMES = 15
VARIANTS = ("production", "by case", "by case, NB")
POSITIONS = ("DEF", "MID")


def threshold(position: str) -> int:
    return config.DC_THRESHOLD_DEF if position == "DEF" else config.DC_THRESHOLD_MID_FWD


def fit_sizes(rows: Iterable[dict]) -> dict:
    """Rule 1. {position: negative-binomial size} from per-match counts in full games.

    NB2 has variance = mean + mean^2 / size. Pooled over players by least squares on the excess
    variance: size = sum(mean^4) / sum((var - mean) x mean^2)."""
    counts: dict = defaultdict(list)
    for r in rows:
        if r["position"] in ("DEF", "MID", "FWD") and r["minutes"] >= FULL_GAME:
            group = "DEF" if r["position"] == "DEF" else "MID/FWD"
            counts[(group, r["element"])].append(r["dc"])
    out = {}
    for group in ("DEF", "MID/FWD"):
        num = den = 0.0
        for (g, _el), cs in counts.items():
            if g != group or len(cs) < MIN_FULL_GAMES:
                continue
            m = statistics.fmean(cs)
            v = statistics.variance(cs)
            num += m ** 4
            den += (v - m) * m ** 2
        if den <= 0:
            raise ValueError(f"{group}: no overdispersion to fit")
        out[group] = round(num / den)
    return {"DEF": out["DEF"], "MID": out["MID/FWD"], "FWD": out["MID/FWD"]}


def brier_by_gw(cases: Iterable[tuple], season: str) -> dict:
    """{(season, gw): {"sq", "n", "p", "hit", "keys"}} from (gw, element, opponent, position, p, hit)."""
    out: dict = defaultdict(lambda: {"sq": 0.0, "n": 0, "keys": set(),
                                     "p": dict.fromkeys(POSITIONS, 0.0),
                                     "hit": dict.fromkeys(POSITIONS, 0), "rows": dict.fromkeys(POSITIONS, 0)})
    for gw, element, opponent, position, p, hit in cases:
        if position not in POSITIONS:
            continue
        g = out[(season, gw)]
        g["sq"] += (p - hit) ** 2
        g["n"] += 1
        g["keys"].add((element, opponent))
        g["p"][position] += p
        g["hit"][position] += hit
        g["rows"][position] += 1
    return {k: {**v, "keys": frozenset(v["keys"])} for k, v in out.items()}


def compare_brier(a: dict, b: dict, n_boot: int = N_BOOT, seed: int = 0) -> dict | None:
    """B against A. A negative `diff` means B's probabilities are better."""
    keys = sorted(set(a) & set(b))
    for k in keys:
        if a[k]["keys"] != b[k]["keys"]:
            raise ValueError(f"{k}: the two variants scored different fixtures")
    if not keys:
        return None
    diffs = [(b[k]["sq"] - a[k]["sq"]) / a[k]["n"] for k in keys]
    rng = random.Random(seed)
    boot = sorted(statistics.fmean(rng.choices(diffs, k=len(diffs))) for _ in range(n_boot))
    n = sum(a[k]["n"] for k in keys)

    def calibration(s: dict) -> dict:
        # expected and actual DC points per projected fixture, by position
        out = {}
        for pos in POSITIONS:
            rows = sum(s[k]["rows"][pos] for k in keys)
            out[pos] = {"expected": config.DC_POINTS * sum(s[k]["p"][pos] for k in keys) / rows,
                        "actual": config.DC_POINTS * sum(s[k]["hit"][pos] for k in keys) / rows}
        return out

    return {
        "n_gws": len(keys), "n_rows": n,
        "brier_a": sum(a[k]["sq"] for k in keys) / n, "brier_b": sum(b[k]["sq"] for k in keys) / n,
        "diff": statistics.fmean(diffs),
        "ci": [boot[int(0.025 * n_boot)], boot[min(n_boot - 1, int(0.975 * n_boot))]],
        "calibration_a": calibration(a), "calibration_b": calibration(b),
    }


def choose(brier: dict, spearman: dict, halves: dict) -> dict:
    """Rules 2 and 3. Each argument is {variant: comparison against production}; `halves` is
    {variant: {label: Brier comparison}}."""
    eligible = [v for v in VARIANTS[1:] if spearman[v]["ci"][0] > SPEARMAN_MARGIN]
    if not eligible:
        return {"candidate": None, "eligible": [], "proceed": False}
    candidate = min(eligible, key=lambda v: brier[v]["brier_b"])
    every = all(r["brier_b"] < r["brier_a"] for r in halves[candidate].values())
    return {"candidate": candidate, "eligible": eligible, "proceed": every}


def verdict(brier: dict, spearman: dict) -> str:
    if brier["ci"][0] > 0 or spearman["ci"][1] < 0:
        return "DO NOT SHIP"
    if brier["ci"][1] < 0 and spearman["ci"][0] > SPEARMAN_MARGIN:
        return "SHIP"
    return "INCONCLUSIVE"
