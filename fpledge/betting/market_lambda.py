"""Market-implied expected goals (lambdas) from de-vigged closing odds.

Our own validation found the betting market out-predicts the Dixon-Coles engine on match
outcomes, so the honest move is to USE the market as an input, not bet against it. This
recovers each team's expected goals for a fixture from two market lines:

    over/under 2.5  -> total goals mu = lam_home + lam_away
    1X2 (match odds) -> supremacy s   = lam_home - lam_away

then lam_home = (mu + s) / 2, lam_away = (mu - s) / 2. De-vig first (strip the bookmaker
margin) — comparing to a raw price manufactures a phantom edge (see betting.odds).

Method: solve mu so P(total >= 3) under Poisson(mu) matches the de-vigged P(over 2.5); solve
s so a Poisson scoreline with those lambdas reproduces the de-vigged P(home win). Independent
Poisson is a deliberate simplification for the INVERSION only (the market price already bakes
in low-score dependence); downstream xP/clean-sheet use these lambdas as usual.
"""

from __future__ import annotations

import math

from .odds import proportional_devig, shin_devig

_MAX_GOALS = 12


def _pois(k: int, lam: float) -> float:
    return math.exp(-lam) * lam**k / math.factorial(k)


def _p_over_25(mu: float) -> float:
    """P(total goals >= 3) for total ~ Poisson(mu)."""
    return 1.0 - math.exp(-mu) * (1.0 + mu + mu * mu / 2.0)


def _solve_mu(p_over: float, lo: float = 0.3, hi: float = 6.5) -> float:
    for _ in range(60):  # P(over) is monotincreasing in mu
        mid = 0.5 * (lo + hi)
        if _p_over_25(mid) < p_over:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _p_home_win(lam_home: float, lam_away: float) -> float:
    ph = [_pois(i, lam_home) for i in range(_MAX_GOALS + 1)]
    pa = [_pois(j, lam_away) for j in range(_MAX_GOALS + 1)]
    return sum(ph[i] * pa[j] for i in range(_MAX_GOALS + 1) for j in range(_MAX_GOALS + 1) if i > j)


def _solve_supremacy(mu: float, p_home: float, floor: float = 0.05) -> float:
    lo, hi = -(mu - 2 * floor), (mu - 2 * floor)  # keep both lambdas >= floor
    for _ in range(50):  # P(home win) is monotincreasing in s at fixed mu
        mid = 0.5 * (lo + hi)
        if _p_home_win((mu + mid) / 2, (mu - mid) / 2) < p_home:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def market_lambdas(
    odds_home: float,
    odds_draw: float,
    odds_away: float,
    odds_over25: float,
    odds_under25: float,
    devig: str = "shin",
    floor: float = 0.05,
) -> tuple[float, float]:
    """Return (lam_home, lam_away) implied by closing 1X2 + O/U 2.5 decimal odds."""
    _dv = shin_devig if devig == "shin" else proportional_devig
    p_home, _p_draw, _p_away = _dv([odds_home, odds_draw, odds_away])
    p_over, _p_under = _dv([odds_over25, odds_under25])
    mu = _solve_mu(p_over)
    s = _solve_supremacy(mu, p_home, floor=floor)
    return max((mu + s) / 2, floor), max((mu - s) / 2, floor)
