"""Walk-forward backtest — the honest evaluation loop.

For each gameweek G, fit ONLY on matches before G's first kickoff, predict G, then
score. No shuffling, no future data. Metrics logged to MLflow (lazy import) so the
'iterative feature/algorithm experiments' story is recorded, not asserted.

Betting note: out-of-sample CLV is the single pass/fail metric for the betting arm.
The model is *allowed* to conclude "no edge on EPL 1X2" — that honest null result is
the deliverable, not a failure.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from ..betting import odds as oddsmod
from . import metrics


def _market_devig(m: dict):
    """De-vigged closing 1X2 probabilities for a match, or None if odds absent."""
    o = [m.get("close_h"), m.get("close_d"), m.get("close_a")]
    if any(v is None for v in o):
        return None
    return oddsmod.shin_devig(o)


def walk_forward(
    matches: Sequence[dict],
    test_start_ord: int,
    model_factory: Callable[[], object],
    refit_every: int = 20,
    ev_threshold: float = 0.0,
) -> dict:
    """Expanding-window walk-forward backtest on historical matches.

    For each test match (date_ord >= test_start_ord), predict with a model fit ONLY
    on matches strictly before it (refit every `refit_every` matches for speed).
    Reports the model's log-loss/Brier, the MARKET's de-vigged log-loss/Brier as the
    benchmark to beat, home-win calibration, and an honest ROI from flat-staking every
    positive-EV selection at the closing price (expected ~0/negative on an efficient
    market — that null result is the point).
    """
    matches = sorted(matches, key=lambda m: m["date_ord"])
    test = [m for m in matches if m["date_ord"] >= test_start_ord]

    y_true: list[int] = []
    prob_rows: list[list[float]] = []
    mkt_y: list[int] = []
    mkt_rows: list[list[float]] = []
    hw_p: list[float] = []
    hw_o: list[int] = []
    n_bets = staked = profit = 0.0
    skipped = 0

    model = None
    since_fit = refit_every  # force an initial fit
    for m in test:
        if since_fit >= refit_every:
            train = [x for x in matches if x["date_ord"] < m["date_ord"]]
            model = model_factory().fit(train)
            since_fit = 0
        since_fit += 1

        if not (model.knows(m["home"]) and model.knows(m["away"])):
            skipped += 1
            continue

        p = model.predict(m["home"], m["away"])
        probs = [p.home_win, p.draw, p.away_win]
        y = metrics.outcome_index(m["home_goals"], m["away_goals"])
        prob_rows.append(probs)
        y_true.append(y)
        hw_p.append(p.home_win)
        hw_o.append(1 if y == 0 else 0)

        mkt = _market_devig(m)
        if mkt is not None:
            mkt_rows.append(mkt)
            mkt_y.append(y)

        closing = [m.get("close_h"), m.get("close_d"), m.get("close_a")]
        if all(closing):
            for k, price in enumerate(closing):
                if probs[k] * price - 1.0 > ev_threshold:   # positive EV vs the close
                    n_bets += 1
                    staked += 1
                    profit += (price - 1.0) if y == k else -1.0

    res: dict = {
        "n": len(y_true),
        "skipped_unknown_team": skipped,
        "model_log_loss": metrics.log_loss(y_true, prob_rows) if y_true else None,
        "model_brier": metrics.brier_score(y_true, prob_rows) if y_true else None,
        "calibration_home": metrics.calibration_curve(hw_p, hw_o),
    }
    if mkt_rows:
        res["market_log_loss"] = metrics.log_loss(mkt_y, mkt_rows)
        res["market_brier"] = metrics.brier_score(mkt_y, mkt_rows)
    if staked > 0:
        res["bet_n"] = int(n_bets)
        res["bet_roi"] = profit / staked
        res["bet_profit_units"] = profit
    return res


def run_walk_forward(
    gameweeks: Sequence[int],
    matches_before: Callable[[int], list[dict]],
    fixtures_in: Callable[[int], list[dict]],
    engine_factory: Callable[[], object],
    model_ver: str = "dixon_coles_v0",
    experiment: str | None = "fpledge-backtest",
) -> dict:
    """Run the loop and return aggregate 1X2 metrics.

    Args:
        gameweeks:      ordered gameweeks to evaluate.
        matches_before: gw -> historical matches strictly before that gw (POINT-IN-TIME).
        fixtures_in:    gw -> fixtures to predict; each dict has home, away,
                        home_goals, away_goals (finished results for scoring).
        engine_factory: () -> a fresh match engine exposing .fit(matches).predict(h, a).
    """
    y_true: list[int] = []
    prob_rows: list[list[float]] = []
    home_win_probs: list[float] = []
    home_win_outcomes: list[int] = []

    run = _mlflow_start(experiment, model_ver)
    try:
        for gw in gameweeks:
            engine = engine_factory().fit(matches_before(gw))
            for fx in fixtures_in(gw):
                p = engine.predict(fx["home"], fx["away"])
                prob_rows.append([p.home_win, p.draw, p.away_win])
                y = metrics.outcome_index(fx["home_goals"], fx["away_goals"])
                y_true.append(y)
                home_win_probs.append(p.home_win)
                home_win_outcomes.append(1 if y == 0 else 0)

        results = {
            "n": len(y_true),
            "log_loss": metrics.log_loss(y_true, prob_rows) if y_true else None,
            "brier": metrics.brier_score(y_true, prob_rows) if y_true else None,
            "calibration_home": metrics.calibration_curve(home_win_probs, home_win_outcomes),
        }
        _mlflow_log(run, results)
        return results
    finally:
        _mlflow_end(run)


# --- MLflow helpers (all no-ops if mlflow isn't installed) ------------------ #
def _mlflow_start(experiment, model_ver):  # noqa: ANN001
    try:
        import mlflow  # noqa: PLC0415
    except ImportError:
        return None
    if experiment:
        mlflow.set_experiment(experiment)
    run = mlflow.start_run()
    mlflow.log_param("model_ver", model_ver)
    return run


def _mlflow_log(run, results):  # noqa: ANN001
    if run is None:
        return
    import mlflow  # noqa: PLC0415

    for k in ("log_loss", "brier", "n"):
        if results.get(k) is not None:
            mlflow.log_metric(k, results[k])


def _mlflow_end(run):  # noqa: ANN001
    if run is None:
        return
    import mlflow  # noqa: PLC0415

    mlflow.end_run()
