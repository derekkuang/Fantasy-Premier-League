"""Probabilistic evaluation metrics (stdlib-only).

- log_loss / brier: proper scoring rules for the 1X2 (or any categorical) forecast
- calibration_curve: "when I say 60%, does it happen ~60% of the time?"
- These are the metrics that separate a serious model from a hobby one.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

_EPS = 1e-15


def log_loss(y_true: Sequence[int], prob_rows: Sequence[Sequence[float]]) -> float:
    """Multiclass log loss. y_true[i] is the index of the realised class."""
    if len(y_true) != len(prob_rows):
        raise ValueError("y_true and prob_rows length mismatch")
    total = 0.0
    for y, probs in zip(y_true, prob_rows, strict=True):
        p = min(max(probs[y], _EPS), 1.0 - _EPS)
        total += -math.log(p)
    return total / len(y_true)


def brier_score(y_true: Sequence[int], prob_rows: Sequence[Sequence[float]]) -> float:
    """Multiclass Brier score: mean sum_k (p_k - 1{y=k})^2."""
    total = 0.0
    for y, probs in zip(y_true, prob_rows, strict=True):
        total += sum((p - (1.0 if k == y else 0.0)) ** 2 for k, p in enumerate(probs))
    return total / len(y_true)


def calibration_curve(
    probs: Sequence[float], outcomes: Sequence[int], n_bins: int = 10
) -> list[dict]:
    """Reliability curve for a single binary event (e.g. P(home win)).

    Returns one dict per non-empty bin: mean predicted prob, observed frequency,
    and count. Feed these straight into a reliability diagram.
    """
    bins: list[list[tuple[float, int]]] = [[] for _ in range(n_bins)]
    for p, o in zip(probs, outcomes, strict=True):
        idx = min(int(p * n_bins), n_bins - 1)
        bins[idx].append((p, o))

    curve = []
    for b, items in enumerate(bins):
        if not items:
            continue
        mean_pred = sum(p for p, _ in items) / len(items)
        mean_obs = sum(o for _, o in items) / len(items)
        curve.append(
            {
                "bin": b,
                "mean_pred": mean_pred,
                "mean_obs": mean_obs,
                "count": len(items),
            }
        )
    return curve


def outcome_index(home_goals: int, away_goals: int) -> int:
    """Map a final score to a 1X2 class index: 0=home, 1=draw, 2=away."""
    if home_goals > away_goals:
        return 0
    if home_goals == away_goals:
        return 1
    return 2
