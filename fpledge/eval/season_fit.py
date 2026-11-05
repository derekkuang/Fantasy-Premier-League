"""Should the match engine see the season it is predicting?

WHAT PRODUCTION DOES. `gw.SEASONS` is three completed seasons, so the daily refit fits the same
data every day. Measured across published artifacts from 2026-08-21 to 2026-11-04, the same
future fixture moved by at most 0.0004 expected goals: the engine has learned nothing from this
season. The published validation numbers come from a different configuration again, fitted on the
current season alone (`fpl_backtest.validate_xp`), so this choice has never been measured.

THE REPLAY. Each past season is predicted twice, on the same matches:

  frozen   fitted once on the three seasons before it, never updated. Production today.
  rolling  the same three seasons plus every result of the season so far, as of a cut-off.

A club missing from the fit gets the engine's default rating rather than being skipped, because
that is what production does and because promoted clubs are where this should matter most.

HORIZONS. Market odds now price the next two gameweeks, so the engine only drives fixtures further
out. A forecast for week six is made with today's results, not with last week's, so the rolling fit
is cut off `horizon` days before kickoff. Three and six weeks decide; next-match is for reference.

THE DECISION, WRITTEN BEFORE THE FIRST RUN. Pooled over the seasons tested, at each deciding horizon:

  SHIP           the gap to the closing market narrows with a 95% interval excluding zero, in every
                 season individually as a point estimate, and log-loss is no worse as a point
                 estimate. The market gap decides because it is far less noisy than results and
                 the closing line is the best estimate of the true probabilities available.
  DO NOT SHIP    log-loss or the market gap is worse with an interval excluding zero, pooled or in
                 any stage of the season.
  INCONCLUSIVE   anything else. Production stays as it is: a change needs evidence, not its absence.

THE CANDIDATE, FIXED BEFORE THE HELD-OUT RUN. 2023-24 to 2025-26 were used to choose it (HANDOFF
§35), so they cannot also prove it. It is tested once, against production, on 2018-19 to 2022-23,
under the rule above with nothing dropped, the pandemic seasons included. Only SHIP moves it forward,
and then to a live comparison rather than to production. Any other verdict rejects this candidate:
changing a setting and re-running would turn those seasons into development seasons too.
"""

from __future__ import annotations

import math
import random
from bisect import bisect_left
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence

from ..betting.market_lambda import market_lambdas
from ..models.dixon_coles import DixonColesModel
from . import metrics
from .backtest import _market_devig

PRIOR_SEASONS = 3                # `gw.SEASONS` is three
HORIZONS = (0, 21, 42)           # days between the data cut-off and kickoff
DECIDING_HORIZONS = (21, 42)
METRICS = ("log_loss", "market_gap", "lam_gap")
STAGES = ((1, 4), (5, 10), (11, 19), (20, 38))
N_BOOT = 2000
CANDIDATE_HALF_LIFE = 270.0
CANDIDATE_MIN_GAMES = 10


class CandidateEngine(DixonColesModel):
    """The engine under test: a longer memory, and no rating until a club has played enough.

    New clubs are why the plain rolling fit failed. Rated from a few results, Hull reached Chelsea
    away at 0.01-0.93 expected goals against a market of 2.75-0.71. A club below `min_games` keeps
    the default rating that production already gives a club it has never seen.
    """

    def __init__(self, half_life_days: float = CANDIDATE_HALF_LIFE,
                 min_games: int = CANDIDATE_MIN_GAMES):
        super().__init__(half_life_days)
        self.min_games = min_games
        self.games: Counter = Counter()

    def fit(self, matches):
        self.games = Counter(
            team for m in matches
            if m.get("home_goals") is not None and m.get("away_goals") is not None
            for team in (m["home"], m["away"]))
        return super().fit(matches)

    def _strength(self, team: str, a, d):
        if self.games[team] < self.min_games:
            return self.PROMOTED_ATTACK, self.PROMOTED_DEFENCE
        return super()._strength(team, a, d)


def rounds(matches: Sequence[dict]) -> list[int]:
    """Each match's round, as games the busier club has played plus one.

    football-data carries no gameweek, and counting every ten matches drifts after a postponement.
    Expects date order.
    """
    played: dict = defaultdict(int)
    out = []
    for m in matches:
        out.append(1 + max(played[m["home"]], played[m["away"]]))
        played[m["home"]] += 1
        played[m["away"]] += 1
    return out


def stage_of(round_: int) -> str:
    for lo, hi in STAGES:
        if lo <= round_ <= hi:
            return f"{lo}-{hi}"
    return f"{STAGES[-1][0]}-{STAGES[-1][1]}"    # a rearranged game can run past 38 on this count


def _forecast(model, m: dict) -> dict:
    p = model.predict(m["home"], m["away"])
    return {"probs": [p.home_win, p.draw, p.away_win],
            "lam": model.expected_goals(m["home"], m["away"])}


def _market_lam(m: dict):
    odds = [m.get(k) for k in ("close_h", "close_d", "close_a", "close_over25", "close_under25")]
    if any(v is None or v <= 1.0 for v in odds):
        return None
    return market_lambdas(*odds)


def replay_season(matches: Sequence[dict], season: str, model_factory: Callable[[], object],
                  horizons: Sequence[int] = HORIZONS,
                  baseline_factory: Callable[[], object] | None = None) -> list[dict]:
    """One row per match of `season`, carrying both forecasts and what is needed to score them.

    `baseline_factory` builds the frozen fit when it should differ from the rolling one, so that a
    candidate with other settings is measured against production rather than against itself.
    """
    labels = sorted({m["season"] for m in matches})
    prior_labels = labels[max(0, labels.index(season) - PRIOR_SEASONS):labels.index(season)]
    if len(prior_labels) < PRIOR_SEASONS:
        raise ValueError(f"{season} needs {PRIOR_SEASONS} prior seasons, have {prior_labels}")
    prior = [m for m in matches if m["season"] in prior_labels]
    current = sorted((m for m in matches if m["season"] == season), key=lambda m: m["date_ord"])
    dates = [m["date_ord"] for m in current]

    frozen = (baseline_factory or model_factory)().fit(prior)
    # Keyed on how many of this season's results a fit has seen, because that fully determines its
    # training set. With none and no separate baseline it IS the frozen fit: the same object, not a
    # refit of the same data.
    fits: dict[int, object] = {0: frozen if baseline_factory is None else model_factory().fit(prior)}

    rows = []
    for m, round_ in zip(current, rounds(current), strict=True):
        rolling = {}
        for h in horizons:
            n_seen = bisect_left(dates, m["date_ord"] - h)   # strictly before the cut-off
            if n_seen not in fits:
                fits[n_seen] = model_factory().fit(prior + current[:n_seen])
            rolling[h] = _forecast(fits[n_seen], m)
        rows.append({
            "season": season, "date_ord": m["date_ord"], "round": round_,
            "home": m["home"], "away": m["away"],
            "y": metrics.outcome_index(m["home_goals"], m["away_goals"]),
            "new_club": not (frozen.knows(m["home"]) and frozen.knows(m["away"])),
            "market_probs": _market_devig(m), "market_lam": _market_lam(m),
            "frozen": _forecast(frozen, m), "rolling": rolling,
        })
    return rows


def score(row: dict, forecast: dict, metric: str) -> float | None:
    """One forecast's loss on one match, lower is better. None if the match cannot be scored."""
    if metric == "log_loss":
        return metrics.log_loss([row["y"]], [forecast["probs"]])
    if metric == "market_gap":     # KL divergence from the de-vigged closing line
        mkt = row["market_probs"]
        if mkt is None:
            return None
        return sum(m * math.log(m / max(p, 1e-15))
                   for m, p in zip(mkt, forecast["probs"], strict=True) if m > 0)
    if metric == "lam_gap":        # expected goals per side away from the closing line
        mkt = row["market_lam"]
        if mkt is None:
            return None
        return (abs(forecast["lam"][0] - mkt[0]) + abs(forecast["lam"][1] - mkt[1])) / 2
    raise ValueError(f"unknown metric {metric!r}")


def _interval(blocks: dict, n_boot: int, seed: int) -> tuple[float, float]:
    """95% bootstrap interval on a mean, resampling whole weeks.

    Matches in a week share the team-strength errors of the fits behind them, so resampling single
    matches would claim more independence than exists and an interval narrower than it should be.
    """
    totals = [(sum(v), len(v)) for v in blocks.values()]
    rng = random.Random(seed)
    means = []
    for _ in range(n_boot):
        drawn = rng.choices(totals, k=len(totals))
        means.append(sum(t for t, _ in drawn) / sum(n for _, n in drawn))
    means.sort()
    return means[int(0.025 * n_boot)], means[min(n_boot - 1, int(0.975 * n_boot))]


def compare(rows: Sequence[dict], horizon: int, metric: str, n_boot: int = N_BOOT,
            seed: int = 0) -> dict | None:
    """Rolling against frozen on the same matches. A negative `diff` means rolling is better."""
    blocks: dict = defaultdict(list)
    frozen_total = rolling_total = 0.0
    for r in rows:
        a, b = score(r, r["frozen"], metric), score(r, r["rolling"][horizon], metric)
        if a is None or b is None:
            continue
        frozen_total += a
        rolling_total += b
        # Tuesday to Monday, so a weekend round stays in one block.
        blocks[(r["season"], (r["date_ord"] - 2) // 7)].append(b - a)
    n = sum(len(v) for v in blocks.values())
    if not n:
        return None
    lo, hi = _interval(blocks, n_boot, seed)
    return {"n": n, "frozen": frozen_total / n, "rolling": rolling_total / n,
            "diff": (rolling_total - frozen_total) / n, "ci": [lo, hi]}


def _breakdown(rows: Sequence[dict], horizon: int, metric: str, n_boot: int) -> dict:
    def run(subset):
        return compare(subset, horizon, metric, n_boot)

    return {
        "pooled": run(rows),
        "seasons": {s: run([r for r in rows if r["season"] == s])
                    for s in sorted({r["season"] for r in rows})},
        "stages": {s: run([r for r in rows if stage_of(r["round"]) == s])
                   for s in (f"{lo}-{hi}" for lo, hi in STAGES)},
        "new_clubs": run([r for r in rows if r["new_club"]]),
        "known_clubs": run([r for r in rows if not r["new_club"]]),
    }


def summarise(rows: Sequence[dict], horizons: Sequence[int] = HORIZONS, n_boot: int = N_BOOT) -> dict:
    out: dict = {"seasons": sorted({r["season"] for r in rows}), "n_matches": len(rows),
                 "horizons": {h: {m: _breakdown(rows, h, m, n_boot) for m in METRICS}
                              for h in horizons}}
    market = [r for r in rows if r["market_probs"] is not None]
    out["market_log_loss"] = (
        metrics.log_loss([r["y"] for r in market], [r["market_probs"] for r in market])
        if market else None)
    return out


def verdict(summary: dict, deciding: Sequence[int] = DECIDING_HORIZONS) -> dict:
    """The rule from the module docstring, applied mechanically."""
    worse, not_shown = [], []
    for h in deciding:
        block = summary["horizons"][h]
        for metric in ("log_loss", "market_gap"):
            if block[metric]["pooled"]["ci"][0] > 0:
                worse.append(f"{h}d: {metric} worse, pooled")
            for stage, res in block[metric]["stages"].items():
                if res is not None and res["ci"][0] > 0:
                    worse.append(f"{h}d: {metric} worse in rounds {stage}")
        gap, loss = block["market_gap"], block["log_loss"]
        if gap["pooled"]["ci"][1] >= 0:
            not_shown.append(f"{h}d: market gap interval includes zero")
        not_shown += [f"{h}d: market gap did not narrow in {s}"
                      for s, res in gap["seasons"].items() if res["diff"] >= 0]
        if loss["pooled"]["diff"] > 0:
            not_shown.append(f"{h}d: log-loss worse as a point estimate")
    if worse:
        return {"decision": "DO NOT SHIP", "reasons": worse}
    if not_shown:
        return {"decision": "INCONCLUSIVE", "reasons": not_shown}
    return {"decision": "SHIP", "reasons": []}
