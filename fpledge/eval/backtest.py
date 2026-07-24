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

from . import metrics


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
