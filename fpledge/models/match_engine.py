"""The shared match engine: team scoring rates -> a scoreline probability matrix.

The scoreline matrix is the ONE object the whole system is built on. Every betting
market (1X2, BTTS, over/under, correct score) and the FPL clean-sheet probability
are just sums over its cells:

    P(home win)      = sum P[i, j]  for i > j
    P(BTTS)          = sum P[i, j]  for i >= 1 and j >= 1
    P(over 2.5)      = sum P[i, j]  for i + j >= 3
    P(home CS)       = sum P[i, 0]  == P(away scores 0)     <- feeds FPL

The matrix math is stdlib-only and fully tested. Fitting the team attack/defence
ratings is delegated to `penaltyblog` (Dixon-Coles with time decay) when it is
installed; a crude average-goals fallback keeps the pipeline runnable without it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .. import config


def poisson_pmf(k: int, lam: float) -> float:
    """P(X = k) for X ~ Poisson(lam)."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * lam**k / math.factorial(k)


def _dixon_coles_tau(i: int, j: int, lam: float, mu: float, rho: float) -> float:
    """Low-score dependence correction (Dixon & Coles, 1997)."""
    if i == 0 and j == 0:
        return 1.0 - lam * mu * rho
    if i == 0 and j == 1:
        return 1.0 + lam * rho
    if i == 1 and j == 0:
        return 1.0 + mu * rho
    if i == 1 and j == 1:
        return 1.0 - rho
    return 1.0


def scoreline_matrix(
    lam_home: float, lam_away: float, rho: float = 0.0, max_goals: int = config.MAX_GOALS
) -> list[list[float]]:
    """(max_goals+1) x (max_goals+1) matrix P[i][j] = P(home i, away j).

    Applies the Dixon-Coles low-score correction and renormalises so the truncated
    matrix sums to exactly 1.
    """
    m = [
        [
            poisson_pmf(i, lam_home)
            * poisson_pmf(j, lam_away)
            * _dixon_coles_tau(i, j, lam_home, lam_away, rho)
            for j in range(max_goals + 1)
        ]
        for i in range(max_goals + 1)
    ]
    total = sum(sum(row) for row in m)
    return [[cell / total for cell in row] for row in m]


@dataclass
class MatchProbabilities:
    """Everything the rest of the system consumes, derived from one matrix."""

    lam_home: float
    lam_away: float
    home_win: float
    draw: float
    away_win: float
    btts: float
    over_2_5: float
    clean_sheet_home: float
    clean_sheet_away: float
    most_likely_score: tuple[int, int]
    matrix: list[list[float]]


def derive(lam_home: float, lam_away: float, rho: float = config.DIXON_COLES_RHO) -> MatchProbabilities:
    """Compute all derived market/FPL probabilities from expected goals."""
    m = scoreline_matrix(lam_home, lam_away, rho)
    n = len(m)

    home_win = sum(m[i][j] for i in range(n) for j in range(n) if i > j)
    draw = sum(m[i][i] for i in range(n))
    away_win = sum(m[i][j] for i in range(n) for j in range(n) if i < j)
    btts = sum(m[i][j] for i in range(1, n) for j in range(1, n))
    over_2_5 = sum(m[i][j] for i in range(n) for j in range(n) if i + j >= 3)
    clean_sheet_home = sum(m[i][0] for i in range(n))   # away scores 0
    clean_sheet_away = sum(m[0][j] for j in range(n))   # home scores 0

    best_ij, best_p = (0, 0), -1.0
    for i in range(n):
        for j in range(n):
            if m[i][j] > best_p:
                best_p, best_ij = m[i][j], (i, j)

    return MatchProbabilities(
        lam_home=lam_home,
        lam_away=lam_away,
        home_win=home_win,
        draw=draw,
        away_win=away_win,
        btts=btts,
        over_2_5=over_2_5,
        clean_sheet_home=clean_sheet_home,
        clean_sheet_away=clean_sheet_away,
        most_likely_score=best_ij,
        matrix=m,
    )


class DixonColesEngine:
    """Fits team attack/defence ratings and predicts expected goals per fixture.

    Prefers `penaltyblog` (proper Dixon-Coles MLE with exponential time decay).
    Without it, falls back to a crude league/team average-goals baseline so the
    end-to-end pipeline still runs — clearly NOT an edge, just a placeholder.
    """

    def __init__(self, rho: float = config.DIXON_COLES_RHO):
        self.rho = rho
        self._pb_model = None  # penaltyblog model when available
        self._fallback = None  # (avg_for, avg_against, home_adv) baseline

    def fit(self, matches, half_life_days: float = 180.0):  # noqa: ANN001
        """Fit on historical matches.

        `matches` is an iterable of dicts with keys:
            home, away, home_goals, away_goals, date (ISO str)
        Point-in-time discipline is the caller's job: only pass matches that
        kicked off strictly before the fixture you intend to predict.
        """
        try:
            import pandas as pd  # noqa: PLC0415
            import penaltyblog as pb  # noqa: PLC0415
        except ImportError:
            self._fit_fallback(matches)
            return self

        df = pd.DataFrame(list(matches))
        weights = pb.models.dixon_coles_weights(df["date"], half_life_days)
        self._pb_model = pb.models.DixonColesGoalModel(
            df["home_goals"], df["away_goals"], df["home"], df["away"], weights
        )
        self._pb_model.fit()
        return self

    def _fit_fallback(self, matches) -> None:  # noqa: ANN001
        rows = list(matches)
        if not rows:
            self._fallback = (1.3, 1.3, 0.25)
            return
        hg = sum(r["home_goals"] for r in rows) / len(rows)
        ag = sum(r["away_goals"] for r in rows) / len(rows)
        self._fallback = (hg, ag, max(hg - ag, 0.0))

    def expected_goals(self, home: str, away: str) -> tuple[float, float]:  # noqa: ARG002
        if self._pb_model is not None:
            p = self._pb_model.predict(home, away)
            # penaltyblog exposes expected goals on the prediction object.
            return float(p.home_goal_expectation), float(p.away_goal_expectation)
        avg_for, avg_against, home_adv = self._fallback
        return avg_for + home_adv / 2, avg_against - home_adv / 2

    def predict(self, home: str, away: str) -> MatchProbabilities:
        lam_h, lam_a = self.expected_goals(home, away)
        return derive(lam_h, lam_a, self.rho)
