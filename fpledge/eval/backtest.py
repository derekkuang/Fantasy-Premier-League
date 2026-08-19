"""Walk-forward backtest — the honest evaluation loop.

Point-in-time: each prediction uses a model fit ONLY on matches strictly before it
(refit every `refit_every` matches; smaller = fairer vs an always-current market
close, at higher runtime). The model is compared to the de-vigged closing line on the
SAME odds-present matches (never full-sample-model vs odds-subset-market), home-win
calibration is reported, and the flat-stake ROI-vs-closing carries a standard error so
a positive ROI that is really noise shows up as "consistent with zero".

CLV, not this backtest ROI, is the true live betting metric. On EPL 1X2 the honest
expected result is: model ≈ market, with no beatable edge.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

from ..betting import odds as oddsmod
from . import metrics


def _market_devig(m: dict):
    """De-vigged closing 1X2 probs, or None if any price is missing/invalid (<=1.0).

    The `v <= 1.0` guard rejects void/sentinel prices (0.0, 1.0) that would otherwise
    raise inside `implied_prob` and abort the whole run — and keeps this consistent
    with the `all(closing)` guard used by the betting sim.
    """
    o = [m.get("close_h"), m.get("close_d"), m.get("close_a")]
    if any(v is None or v <= 1.0 for v in o):
        return None
    return oddsmod.shin_devig(o)


def walk_forward(
    matches: Sequence[dict],
    test_start_ord: int,
    model_factory: Callable[[], object],
    refit_every: int = 10,
    ev_threshold: float = 0.0,
    experiment: str | None = None,
    model_ver: str = "dixon_coles_v1",
) -> dict:
    """Expanding-window walk-forward backtest on historical matches."""
    matches = sorted(matches, key=lambda m: m["date_ord"])
    test = [m for m in matches if m["date_ord"] >= test_start_ord]

    y_true: list[int] = []
    prob_rows: list[list[float]] = []           # full known-team set (calibration/full LL)
    mdl_y: list[int] = []
    mdl_rows: list[list[float]] = []            # model on odds-present rows (fair head-to-head)
    mkt_y: list[int] = []
    mkt_rows: list[list[float]] = []            # de-vigged market on the SAME rows
    hw_p: list[float] = []
    hw_o: list[int] = []

    n_bets = 0
    profit = 0.0
    profit_sq = 0.0
    skipped = 0
    n_fits = 0
    n_nonconverged = 0

    model = None
    since_fit = refit_every  # force an initial fit
    for m in test:
        if since_fit >= refit_every:
            train = [x for x in matches if x["date_ord"] < m["date_ord"]]
            if not train:            # nothing to learn from yet — skip, don't crash
                skipped += 1
                continue
            model = model_factory().fit(train)
            n_fits += 1
            if not getattr(model, "converged", True):
                n_nonconverged += 1
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
            mdl_rows.append(probs)   # score the model on EXACTLY the market's rows
            mdl_y.append(y)
            closing = [m["close_h"], m["close_d"], m["close_a"]]
            for k, price in enumerate(closing):
                if probs[k] * price - 1.0 > ev_threshold:   # positive EV vs the close
                    pnl = (price - 1.0) if y == k else -1.0
                    n_bets += 1
                    profit += pnl
                    profit_sq += pnl * pnl

    res: dict = {
        "n": len(y_true),
        "n_with_odds": len(mkt_y),
        "skipped_unknown_team": skipped,
        "n_fits": n_fits,
        "n_nonconverged_fits": n_nonconverged,
        "model_log_loss": metrics.log_loss(y_true, prob_rows) if y_true else None,
        "model_brier": metrics.brier_score(y_true, prob_rows) if y_true else None,
        "calibration_home": metrics.calibration_curve(hw_p, hw_o),
    }
    if mkt_rows:
        # Fair head-to-head: model and market scored on identical (odds-present) rows.
        res["model_log_loss_h2h"] = metrics.log_loss(mdl_y, mdl_rows)
        res["market_log_loss"] = metrics.log_loss(mkt_y, mkt_rows)
        res["model_brier_h2h"] = metrics.brier_score(mdl_y, mdl_rows)
        res["market_brier"] = metrics.brier_score(mkt_y, mkt_rows)
    if n_bets > 0:
        roi = profit / n_bets                    # unit stakes -> ROI == mean pnl
        var = max(profit_sq / n_bets - roi * roi, 0.0)
        res["bet_n"] = n_bets
        res["bet_roi"] = roi
        res["bet_roi_se"] = math.sqrt(var / n_bets)   # SE of the ROI estimate
        res["bet_profit_units"] = profit

    _mlflow_log_run(experiment, model_ver, res)
    return res


def _mlflow_log_run(experiment: str | None, model_ver: str, res: dict) -> None:
    """Log the backtest to MLflow if configured and installed (else a no-op)."""
    if experiment is None:
        return
    try:
        import mlflow
    except ImportError:
        return
    mlflow.set_experiment(experiment)
    with mlflow.start_run():
        mlflow.log_param("model_ver", model_ver)
        for k in (
            "n", "n_with_odds", "model_log_loss", "model_log_loss_h2h",
            "market_log_loss", "model_brier", "bet_roi",
        ):
            if res.get(k) is not None:
                mlflow.log_metric(k, res[k])
