#!/usr/bin/env python3
"""Hunt for ranking edge the six earlier A/Bs didn't find.

The recorded conclusion is that the model hit a discrimination ceiling: played-only per-GW
Spearman 0.338 against FPL's 0.587, with recency-xG, returns-bonus and LightGBM all null or
worse. That conclusion came from experiments that each changed the MODEL and re-ran the whole
walk-forward — expensive, so few of them ran.

There is a cheaper and so far unexplored axis. `validate_xp(return_records=True)` hands back
`(gw, element, my_xp, fpl_xp, actual, pos, minutes)` for every scored player-gameweek. Given
that table, any transformation of the existing predictions can be scored WITHOUT refitting
anything: blends, per-position recalibration, rank averaging, subgroup diagnostics. One slow
run, then as many experiments as you like.

Two rules this script holds itself to:

  NO TUNING ON THE TEST SET. Gameweeks are split in half by time. Anything with a parameter is
  fitted on the early half and scored on the late half, and both numbers are printed. A blend
  weight chosen on the data it is then evaluated on is not a result.

  MONOTONE TRANSFORMS ARE NOT TESTED. Spearman is rank correlation, so it is invariant to any
  monotone rescaling. "The model is under-dispersed" is true (its MAE is LOWER than FPL's while
  its ranking is worse) but stretching the distribution cannot move Spearman by construction.
  Anything that helps has to change the ORDER.

Usage:
  python scripts/model_search.py                 # uses the cached records if present
  python scripts/model_search.py --refresh       # re-run the walk-forward (slow)
"""

from __future__ import annotations

import json
import math
import pathlib
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpledge import config
from fpledge.eval.fpl_backtest import validate_xp
from fpledge.ingest import vaastav

# 2025-26 carries FPL's own projection for only 4 of 30 gameweeks — the column is empty for
# the rest — which is too thin a baseline to search against. 2024-25 has 35 of 38.
SEASON = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "2024-25"
CACHE = config.DATA_DIR / "eval" / f"records_{SEASON}.json"
MIN_GROUP = 10        # a gameweek needs this many players to rank-correlate meaningfully


# --- data ------------------------------------------------------------------------------ #
def load_records(refresh: bool = False) -> list[list]:
    if CACHE.exists() and not refresh:
        return json.loads(CACHE.read_text())
    print(f"running the walk-forward for {SEASON} (slow, once)...")
    rows = vaastav.fetch_player_gws(SEASON)
    fixtures = vaastav.fetch_fixtures(SEASON)
    teams = vaastav.fetch_teams(SEASON)
    _, records = validate_xp(
        rows, fixtures, teams, burn_in=8, minutes_mode="recent",
        bonus_mode="rate", return_records=True,
    )
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps([list(r) for r in records]))
    print(f"  cached {len(records)} records -> {CACHE}")
    return [list(r) for r in records]


# --- scoring --------------------------------------------------------------------------- #
def spearman_by_gw(recs: list[list], score) -> float | None:
    """Mean per-gameweek Spearman of `score(record)` against realised points.

    Per gameweek, not pooled: pooling would let the model score well simply by knowing that
    gameweeks differ in overall scoring, which tells a manager nothing about who to pick.
    """
    import scipy.stats as st

    per_gw: dict = defaultdict(list)
    for r in recs:
        per_gw[r[0]].append(r)
    out = []
    for g in per_gw.values():
        if len(g) < MIN_GROUP:
            continue
        pred = [score(r) for r in g]
        act = [r[4] for r in g]
        if len(set(pred)) < 2 or len(set(act)) < 2:
            continue
        rho = st.spearmanr(pred, act).correlation
        if not math.isnan(rho):
            out.append(rho)
    return statistics.mean(out) if out else None


def ranks_within_gw(recs: list[list], idx: int) -> dict:
    """Percentile rank of each record within its own gameweek, for rank-space blending."""
    import scipy.stats as st

    per_gw: dict = defaultdict(list)
    for i, r in enumerate(recs):
        per_gw[r[0]].append(i)
    out: dict[int, float] = {}
    for idxs in per_gw.values():
        vals = [recs[i][idx] for i in idxs]
        rk = st.rankdata(vals) / max(len(vals), 1)
        for i, v in zip(idxs, rk, strict=True):
            out[i] = float(v)
    return out


def zscores_within_gw(recs: list[list], idx: int) -> dict:
    """Standardise within gameweek, so two differently-scaled predictors can be averaged."""
    per_gw: dict = defaultdict(list)
    for i, r in enumerate(recs):
        per_gw[r[0]].append(i)
    out: dict[int, float] = {}
    for idxs in per_gw.values():
        vals = [recs[i][idx] for i in idxs]
        mu = statistics.mean(vals)
        sd = statistics.pstdev(vals) or 1.0
        for i in idxs:
            out[i] = (recs[i][idx] - mu) / sd
    return out


def split_by_time(recs: list[list]) -> tuple[list[list], list[list]]:
    """Early gameweeks to fit on, late gameweeks to be judged on."""
    gws = sorted({r[0] for r in recs})
    cut = gws[len(gws) // 2]
    return [r for r in recs if r[0] < cut], [r for r in recs if r[0] >= cut]


def fmt(x) -> str:
    return "  n/a" if x is None else f"{x:.3f}"


# --- the experiments -------------------------------------------------------------------- #
def diagnose(played: list[list]) -> None:
    """Before trying to fix it, find out where it is losing."""
    print("\n" + "=" * 74)
    print("DIAGNOSTIC — where does the ranking actually go wrong?")
    print("=" * 74)

    print(f"\n{'subgroup':<26}{'n':>7}{'ours':>9}{'FPL':>9}{'gap':>9}")
    print("-" * 60)

    def row(label: str, subset: list[list]) -> None:
        if len(subset) < MIN_GROUP:
            return
        m = spearman_by_gw(subset, lambda r: r[2])
        f = spearman_by_gw(subset, lambda r: r[3])
        gap = f"{f - m:+.3f}" if (m is not None and f is not None) else "  n/a"
        print(f"{label:<26}{len(subset):>7}{fmt(m):>9}{fmt(f):>9}{gap:>9}")

    row("all played", played)
    print()
    for pos in ("GK", "DEF", "MID", "FWD"):
        row(f"  {pos}", [r for r in played if r[5] == pos])
    print()
    for lo, hi, label in ((0, 60, "  <60 min"), (60, 85, "  60-85 min"), (85, 999, "  85+ min")):
        row(label, [r for r in played if lo <= r[6] < hi])
    print()
    # Our own projection as a proxy for "is this a premium or a punt" — a manager mostly
    # chooses among plausible picks, so ranking within the top of the board is what counts.
    for lo, hi, label in ((0, 2, "  our xP < 2"), (2, 4, "  our xP 2-4"), (4, 99, "  our xP 4+")):
        row(label, [r for r in played if lo <= r[2] < hi])


def strategies(train: list[list], test: list[list]) -> list[tuple]:
    """Every candidate scorer, fitted on `train` and reported on both halves."""
    out: list[tuple] = []

    def add(name: str, make, note: str) -> None:
        tr = spearman_by_gw(train, make(train))
        te = spearman_by_gw(test, make(test))
        out.append((name, tr, te, note))

    add("ours (baseline)", lambda recs: (lambda r: r[2]), "the shipped model")
    add("FPL ep_next", lambda recs: (lambda r: r[3]), "the benchmark")

    # Value-space blend at fixed weights. Both predictors are in points, so this is legitimate
    # without rescaling — but their spreads differ, which is what the z-blend below controls for.
    for w in (0.2, 0.3, 0.4, 0.5, 0.6, 0.8):
        add(f"blend {w:.1f}·ours + {1 - w:.1f}·FPL",
            lambda recs, w=w: (lambda r: w * r[2] + (1 - w) * r[3]),
            "value-space average")

    # Rank-space: immune to the two predictors having different scales or shapes.
    def rank_blend(w: float):
        def make(recs: list[list]):
            a, b = ranks_within_gw(recs, 2), ranks_within_gw(recs, 3)
            idx = {id(r): i for i, r in enumerate(recs)}
            return lambda r: w * a[idx[id(r)]] + (1 - w) * b[idx[id(r)]]
        return make

    for w in (0.3, 0.5, 0.7):
        add(f"rank-blend {w:.1f}/{1 - w:.1f}", rank_blend(w), "average of within-GW ranks")

    # z-space: equalises spread before averaging, which is the right move when one predictor
    # is under-dispersed relative to the other — as ours is.
    def z_blend(w: float):
        def make(recs: list[list]):
            a, b = zscores_within_gw(recs, 2), zscores_within_gw(recs, 3)
            idx = {id(r): i for i, r in enumerate(recs)}
            return lambda r: w * a[idx[id(r)]] + (1 - w) * b[idx[id(r)]]
        return make

    for w in (0.3, 0.5, 0.7):
        add(f"z-blend {w:.1f}/{1 - w:.1f}", z_blend(w), "standardise within GW, then average")

    return out


def per_position_blend(train: list[list], test: list[list]) -> None:
    """Fit one blend weight per position on the early half, apply it to the late half.

    The diagnostic above shows the gap is not uniform across positions. If it is much larger
    for one, a single global weight is leaving something on the table.
    """
    print("\n" + "=" * 74)
    print("PER-POSITION BLEND — weight fitted on early GWs, scored on late GWs")
    print("=" * 74)

    grid = [i / 10 for i in range(11)]
    best: dict[str, float] = {}
    print(f"\n{'position':<12}{'best w (ours)':>16}{'train':>9}{'test @w':>10}{'test ours':>11}{'test FPL':>10}")
    print("-" * 68)
    for pos in ("GK", "DEF", "MID", "FWD"):
        tr = [r for r in train if r[5] == pos]
        te = [r for r in test if r[5] == pos]
        if len(tr) < MIN_GROUP or len(te) < MIN_GROUP:
            continue
        scored = [(spearman_by_gw(tr, lambda r, w=w: w * r[2] + (1 - w) * r[3]) or -9, w) for w in grid]
        s, w = max(scored)
        best[pos] = w
        te_w = spearman_by_gw(te, lambda r, w=w: w * r[2] + (1 - w) * r[3])
        te_m = spearman_by_gw(te, lambda r: r[2])
        te_f = spearman_by_gw(te, lambda r: r[3])
        print(f"{pos:<12}{w:>16.1f}{fmt(s):>9}{fmt(te_w):>10}{fmt(te_m):>11}{fmt(te_f):>10}")

    if best:
        combined = spearman_by_gw(
            test, lambda r: best.get(r[5], 0.5) * r[2] + (1 - best.get(r[5], 0.5)) * r[3]
        )
        flat = spearman_by_gw(test, lambda r: r[3])
        print(f"\n  all positions, per-position weights, TEST half: {fmt(combined)}")
        print(f"  FPL alone on the same half:                    {fmt(flat)}")


def main() -> None:
    refresh = "--refresh" in sys.argv
    recs = load_records(refresh)
    print(f"season {SEASON}")
    played = [r for r in recs if r[6] > 0]
    # A gameweek with a constant (empty) FPL column is not a comparison — drop it from the
    # whole search rather than letting it silently average in on one side only.
    by_gw: dict = defaultdict(list)
    for r in played:
        by_gw[r[0]].append(r)
    dropped = [gw for gw, g in by_gw.items() if len({x[3] for x in g}) < 2]
    if dropped:
        print(f"dropping {len(dropped)} gameweek(s) with no FPL baseline: {sorted(dropped)}")
        played = [r for r in played if r[0] not in set(dropped)]
    gws = sorted({r[0] for r in played})
    print(f"\n{len(recs)} scored records, {len(played)} with minutes, GW{gws[0]}-{gws[-1]}")

    diagnose(played)

    train, test = split_by_time(played)
    print("\n" + "=" * 74)
    print("STRATEGY SEARCH — fitted nowhere, scored on both halves")
    print(f"  train GW{min(r[0] for r in train)}-{max(r[0] for r in train)} ({len(train)} recs)"
          f"   test GW{min(r[0] for r in test)}-{max(r[0] for r in test)} ({len(test)} recs)")
    print("=" * 74)
    print(f"\n{'strategy':<30}{'train':>9}{'test':>9}   note")
    print("-" * 74)
    rows = strategies(train, test)
    base_test = next(t for n, _, t, _ in rows if n == "ours (baseline)")
    fpl_test = next(t for n, _, t, _ in rows if n == "FPL ep_next")
    for name, tr, te, note in rows:
        mark = ""
        if te is not None and fpl_test is not None and te > fpl_test:
            mark = "  <<< beats FPL"
        elif te is not None and base_test is not None and te > base_test:
            mark = "  < beats ours"
        print(f"{name:<30}{fmt(tr):>9}{fmt(te):>9}   {note}{mark}")

    per_position_blend(train, test)

    print("\n" + "=" * 74)
    print("Read the TEST column only. The train column is there to show whether a strategy")
    print("held up out of sample or just fitted the half it was chosen on.")
    print("=" * 74)


if __name__ == "__main__":
    main()
