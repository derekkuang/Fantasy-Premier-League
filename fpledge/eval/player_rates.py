"""Should player rates update during the season?

WHAT PRODUCTION DOES. A player's per-90 xG, xA, defensive contribution and bonus come from last
season's totals and never change. A player with under 270 Premier League minutes last season gets
zero for all four, so he is projected to score and assist nothing however he plays. On 2026-11-13
that was 53 of the 208 players with 450+ minutes this season, Nicolas Jackson among them (six
goals). Each club's expected goals are split among the players who do have a rate, so the zeros
also inflate their teammates.

THE VARIANTS. Everything else is held fixed: the minutes model, and expected goals per side, which
come from closing odds so the comparison isolates the rates rather than early-season engine noise.

  production     last season's per-90s, zero below 270 minutes, all season
  this season    season-to-date per-90s only, zero below 270 minutes (the harness's old default)
  blend k        (this season's total + k x prior) / (this season's 90s + k). The prior is last
                 season's per-90 at 270+ minutes, otherwise the per-90 of last season's regulars
                 at the player's position. k is how many full games the prior is worth.
  blend, recent  the chosen blend with this season's games weighted by a 6-gameweek half-life:
                 the "form" version. Recency on xG/xA alone measured +0.002 in July 2026.

Scored per gameweek from GW2 on players who played: Spearman rank correlation of projected
against actual points, and mean absolute error. Every variant is scored on exactly the same rows.

THE DECISION, WRITTEN BEFORE ANY RUN (2026-11-13).

  Development, 2023-24 to 2025-26. These have FPL xG and a season before them to take a prior
  from. They were used in earlier player-model work, so they choose; they do not prove.
    1. k is the value in K_GRID with the highest pooled per-gameweek Spearman.
    2. The recent version replaces it only if it beats that blend with a 95% interval above zero.
    3. The candidate goes to the held-out test only if it beats production pooled and in every
       development season, as point estimates. Otherwise stop: production stays.

  Held out, 2026-27 GW2 onwards, run once (`compare_player_rates.py --held-out`):
    SHIP           Spearman better than production with a 95% interval above zero, and mean
                   absolute error no worse as a point estimate.
    DO NOT SHIP    Spearman worse with a 95% interval below zero.
    INCONCLUSIVE   anything else. Production stays. Rerun when more gameweeks exist only under a
                   new pre-registration, never by moving this one's bar.

Intervals are a bootstrap over whole gameweeks, because players in one gameweek share fixtures.
"""

from __future__ import annotations

import random
import statistics
from collections import defaultdict
from collections.abc import Iterable, Sequence

from ..betting.market_lambda import market_lambdas
from ..models.teammap import build_team_map

STATS = ("xg", "xa", "dc", "bonus")
MIN_PRIOR_MINUTES = 270          # production's threshold (`models.xp_table.MIN_RATE_MINUTES`)
K_GRID = (3, 6, 10, 20)
RECENCY_HALF_LIFE = 6.0          # gameweeks
BURN_IN = 1                      # score from GW2: the harness needs one gameweek of minutes
N_BOOT = 2000
_ZERO = dict.fromkeys(STATS, 0.0)


def priors(previous: Iterable[dict], players: dict, fill: str) -> dict:
    """{element: {stat: per 90}} from last season's totals.

    `players` is {element: (code, position)} for the season being predicted. `fill` decides what a
    player without 270 minutes last season gets: "zero", as production does, or "position", the
    per-90 of last season's regulars at his position.
    """
    previous = list(previous)
    by_code = {p["code"]: p for p in previous}
    totals: dict = defaultdict(lambda: dict(_ZERO))
    nineties: dict = defaultdict(float)
    for p in previous:
        if p["minutes"] >= MIN_PRIOR_MINUTES and p["position"]:
            for s in STATS:
                totals[p["position"]][s] += p[s]
            nineties[p["position"]] += p["minutes"] / 90.0
    position_mean = {pos: {s: totals[pos][s] / n for s in STATS} for pos, n in nineties.items()}

    out = {}
    for element, (code, position) in players.items():
        last = by_code.get(code)
        if last and last["minutes"] >= MIN_PRIOR_MINUTES:
            out[element] = {s: last[s] / (last["minutes"] / 90.0) for s in STATS}
        elif fill == "position":
            out[element] = dict(position_mean.get(position, _ZERO))
        else:
            out[element] = dict(_ZERO)
    return out


def market_fixture_lambdas(fd_matches: Iterable[dict], teams_name_to_id: dict) -> dict:
    """{(home_id, away_id): (lam_home, lam_away)} from football-data's closing odds."""
    fd_matches = list(fd_matches)
    fd_names = sorted({m["home"] for m in fd_matches} | {m["away"] for m in fd_matches})
    tmap = build_team_map(list(teams_name_to_id), fd_names)
    fd_to_id = {fd: teams_name_to_id[name] for name, fd in tmap.items() if fd}
    out = {}
    for m in fd_matches:
        home, away = fd_to_id.get(m["home"]), fd_to_id.get(m["away"])
        odds = (m["close_h"], m["close_d"], m["close_a"], m["close_over25"], m["close_under25"])
        if home is None or away is None or any(v is None or v <= 1.0 for v in odds):
            continue
        out[(home, away)] = market_lambdas(*odds)
    return out


def gw_scores(records: Sequence[tuple], season: str) -> dict:
    """{(season, gw): {"rho", "abs_err", "n", "keys"}} over players who played.

    `records` are `validate_xp`'s (gw, element, xp, fpl_xp, actual, position, minutes) tuples.
    """
    import scipy.stats as st

    by_gw: dict = defaultdict(list)
    for gw, element, xp, _fpl, actual, _pos, minutes in records:
        if minutes > 0:
            by_gw[gw].append((element, xp, actual))
    out = {}
    for gw, rows in by_gw.items():
        if len(rows) < 10:
            continue
        rho = st.spearmanr([r[1] for r in rows], [r[2] for r in rows]).correlation
        out[(season, gw)] = {"rho": float(rho), "abs_err": sum(abs(r[1] - r[2]) for r in rows),
                             "n": len(rows), "keys": frozenset(r[0] for r in rows)}
    return out


def compare(a: dict, b: dict, n_boot: int = N_BOOT, seed: int = 0) -> dict | None:
    """B against A on the gameweeks both scored. A positive `diff` means B ranks better."""
    keys = sorted(set(a) & set(b))
    for k in keys:
        if a[k]["keys"] != b[k]["keys"]:
            raise ValueError(f"{k}: the two variants scored different players")
    if not keys:
        return None
    diffs = [b[k]["rho"] - a[k]["rho"] for k in keys]
    rng = random.Random(seed)
    boot = sorted(statistics.fmean(rng.choices(diffs, k=len(diffs))) for _ in range(n_boot))
    rows = sum(a[k]["n"] for k in keys)
    mae_a = sum(a[k]["abs_err"] for k in keys) / rows
    mae_b = sum(b[k]["abs_err"] for k in keys) / rows
    return {
        "n_gws": len(keys), "n_rows": rows,
        "rho_a": statistics.fmean(a[k]["rho"] for k in keys),
        "rho_b": statistics.fmean(b[k]["rho"] for k in keys),
        "diff": statistics.fmean(diffs),
        "ci": [boot[int(0.025 * n_boot)], boot[min(n_boot - 1, int(0.975 * n_boot))]],
        "mae_a": mae_a, "mae_b": mae_b, "mae_diff": mae_b - mae_a,
    }


def blend_name(k: float, recent: bool = False) -> str:
    return f"blend k={k:g}" + (", recent" if recent else "")


def choose(scores: dict) -> dict:
    """Rules 1-3 on the development scores: {variant: {(season, gw): score}}."""
    pooled = {k: statistics.fmean(s["rho"] for s in scores[blend_name(k)].values()) for k in K_GRID}
    k_best = max(K_GRID, key=lambda k: pooled[k])
    plain, recent = blend_name(k_best), blend_name(k_best, recent=True)
    form = compare(scores[plain], scores[recent])
    candidate = recent if form["ci"][0] > 0 else plain

    seasons = sorted({season for season, _gw in scores["production"]})
    vs_prod = compare(scores["production"], scores[candidate])
    by_season = {
        s: compare({k: v for k, v in scores["production"].items() if k[0] == s},
                   {k: v for k, v in scores[candidate].items() if k[0] == s})
        for s in seasons
    }
    proceed = vs_prod["diff"] > 0 and all(r["diff"] > 0 for r in by_season.values())
    return {"k_pooled": pooled, "k": k_best, "recent_vs_plain": form, "candidate": candidate,
            "vs_production": vs_prod, "by_season": by_season, "proceed": proceed}


def verdict(held_out: dict) -> str:
    """The held-out rule. `held_out` is `compare(production, candidate)` on 2026-27."""
    lo, hi = held_out["ci"]
    if lo > 0 and held_out["mae_diff"] <= 0:
        return "SHIP"
    if hi < 0:
        return "DO NOT SHIP"
    return "INCONCLUSIVE"
