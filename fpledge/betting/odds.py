"""Odds utilities: de-vigging and closing-line value (CLV).

CRITICAL CORRECTNESS NOTE
-------------------------
Never compare a raw model probability to a raw bookmaker *price*. A decimal price
of 2.0 does NOT imply a 50% true probability — it implies 50% PLUS the book's
margin (overround, typically ~5% on 1X2). Comparing raw model prob to 1/odds
manufactures a phantom ~2.5%/side "edge" that evaporates live.

Always de-vig first (strip the overround) to recover market-implied probabilities,
THEN compare — and, for betting, shrink the model toward the market before acting.
This module provides the de-vig step and CLV measurement.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def implied_prob(decimal_odds: float) -> float:
    """Raw implied probability of a single decimal price (includes the vig)."""
    if decimal_odds <= 1.0:
        raise ValueError("decimal odds must be > 1.0")
    return 1.0 / decimal_odds


def overround(odds: Sequence[float]) -> float:
    """Book overround (sum of raw implied probs). > 1.0 means a vig is present."""
    return sum(implied_prob(o) for o in odds)


def proportional_devig(odds: Sequence[float]) -> list[float]:
    """Simplest de-vig: normalise raw implied probs to sum to 1.

    Assumes the margin is applied proportionally to each selection. Fast, robust,
    and a fine default. Use `shin_devig` when you suspect favourite-longshot bias.
    """
    raw = [implied_prob(o) for o in odds]
    s = sum(raw)
    return [r / s for r in raw]


def shin_devig(odds: Sequence[float], max_iter: int = 200, tol: float = 1e-12) -> list[float]:
    """Shin (1992) de-vig, which accounts for insider trading / favourite-longshot bias.

    Solves for z in [0, 0.5) such that the recovered true probabilities sum to 1:
        q_i = (sqrt(z^2 + 4(1-z) * pi_i^2 / B) - z) / (2(1-z))
    where pi_i = 1/odds_i (raw implied) and B = sum(pi_i) = overround.
    Falls back to proportional de-vig if no valid z is bracketed.
    """
    raw = [implied_prob(o) for o in odds]
    book = sum(raw)
    if book <= 1.0:  # no vig to remove
        return [r / book for r in raw]

    def q_of_z(z: float) -> list[float]:
        denom = 2.0 * (1.0 - z)
        return [
            (math.sqrt(z * z + 4.0 * (1.0 - z) * (pi * pi) / book) - z) / denom
            for pi in raw
        ]

    # sum(q) is monotonically decreasing in z; at z=0 it equals sqrt(book) > 1.
    lo, hi = 0.0, 0.5
    if sum(q_of_z(hi - 1e-9)) > 1.0:
        return proportional_devig(odds)  # not bracketed; fall back

    mid = 0.0
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        s = sum(q_of_z(mid))
        if abs(s - 1.0) < tol:
            break
        if s > 1.0:
            lo = mid
        else:
            hi = mid
    return q_of_z(mid)


def closing_line_value(odds_taken: float, odds_close: float) -> float:
    """CLV as a fractional price improvement: taken/close - 1.

    Positive => you got a better price than the closing line (good). This is the
    single most important betting-model metric: it converges far faster than ROI
    and is the honest test of whether you have any edge at all.
    """
    return odds_taken / odds_close - 1.0


def novig_clv(
    odds_taken: float, market_close: Sequence[float], selection_idx: int, method: str = "shin"
) -> float:
    """No-vig CLV: your taken price's implied prob vs the de-vigged closing prob.

    Returns (p_taken - p_close_true). Negative is the expected outcome on efficient
    markets and is a *successful*, honest result to report.
    """
    devig = shin_devig if method == "shin" else proportional_devig
    p_close_true = devig(market_close)[selection_idx]
    p_taken = implied_prob(odds_taken)
    return p_taken - p_close_true
