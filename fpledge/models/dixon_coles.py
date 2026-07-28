"""Dixon-Coles goal model — a from-scratch MLE fit (not a library call).

Implements the Dixon & Coles (1997) time-weighted maximum-likelihood fit:

    log λ_home = μ + home_adv + attack[home] + defence[away]
    log λ_away = μ +           attack[away] + defence[home]
    goals ~ Poisson, with the low-score dependence correction τ, and each match
    weighted by exp(-ξ · age) so recent form dominates (ξ from a half-life in days).

Attack/defence are mean-centred inside the objective for identifiability. Fitting is
`scipy.optimize.minimize` (L-BFGS-B) over the weighted negative log-likelihood.

numpy/scipy are declared deps, imported lazily so the stdlib-only core stays
importable; the recovery test uses `pytest.importorskip`.
"""

from __future__ import annotations

from .. import config
from .match_engine import MatchProbabilities, derive


class DixonColesModel:
    # Prior attack/defence for a team the model has never seen (a promoted side): scores a
    # bit below and concedes a bit above league average, ~ a bottom-three team. Lets fixtures
    # against promoted/unknown opponents be predicted instead of skipped (coverage fix #4/#6).
    PROMOTED_ATTACK = -0.25
    PROMOTED_DEFENCE = 0.25

    def __init__(self, half_life_days: float = 180.0):
        self.half_life_days = half_life_days
        self.teams: list[str] = []
        self.idx: dict[str, int] = {}
        self.params = None          # numpy array once fitted
        self.converged: bool = False
        self._n = 0

    def knows(self, team: str) -> bool:
        return team in self.idx

    def fit(self, matches):  # noqa: ANN001
        import numpy as np  # noqa: PLC0415
        from scipy.optimize import minimize  # noqa: PLC0415
        from scipy.special import gammaln  # noqa: PLC0415

        rows = [
            m for m in matches
            if m.get("home_goals") is not None and m.get("away_goals") is not None
        ]
        if not rows:
            raise ValueError("no training matches with results")

        teams = sorted({m["home"] for m in rows} | {m["away"] for m in rows})
        idx = {t: i for i, t in enumerate(teams)}
        n = len(teams)

        hg = np.array([m["home_goals"] for m in rows], dtype=float)
        ag = np.array([m["away_goals"] for m in rows], dtype=float)
        hi = np.array([idx[m["home"]] for m in rows])
        ai = np.array([idx[m["away"]] for m in rows])

        t = np.array([m["date_ord"] for m in rows], dtype=float)
        xi = np.log(2.0) / self.half_life_days
        w = np.exp(-xi * (t.max() - t))

        lg_hg, lg_ag = gammaln(hg + 1), gammaln(ag + 1)
        m00 = (hg == 0) & (ag == 0)
        m01 = (hg == 0) & (ag == 1)
        m10 = (hg == 1) & (ag == 0)
        m11 = (hg == 1) & (ag == 1)

        def neg_ll(p):
            a = p[:n] - p[:n].mean()
            d = p[n : 2 * n] - p[n : 2 * n].mean()
            home_adv, rho, mu = p[2 * n], p[2 * n + 1], p[2 * n + 2]

            log_lh = mu + home_adv + a[hi] + d[ai]
            log_la = mu + a[ai] + d[hi]
            lh, la = np.exp(log_lh), np.exp(log_la)

            ll = (-lh + hg * log_lh - lg_hg) + (-la + ag * log_la - lg_ag)

            tau = np.ones_like(lh)
            tau[m00] = 1.0 - lh[m00] * la[m00] * rho
            tau[m01] = 1.0 + lh[m01] * rho
            tau[m10] = 1.0 + la[m10] * rho
            tau[m11] = 1.0 - rho
            ll = ll + np.log(np.clip(tau, 1e-10, None))

            return -float(np.sum(w * ll))

        x0 = np.zeros(2 * n + 3)
        x0[2 * n] = 0.25                          # home advantage
        x0[2 * n + 1] = config.DIXON_COLES_RHO    # rho prior
        x0[2 * n + 2] = np.log(max(hg.mean(), 0.1))  # baseline log-goals
        bounds = [(-3.0, 3.0)] * (2 * n) + [(-1.0, 1.0), (-0.2, 0.2), (-2.0, 2.0)]

        res = minimize(neg_ll, x0, method="L-BFGS-B", bounds=bounds)
        self.teams, self.idx, self._n = teams, idx, n
        self.params, self.converged = res.x, bool(res.success)
        return self

    def _centred(self):
        import numpy as np  # noqa: PLC0415

        p, n = self.params, self._n
        a = p[:n] - p[:n].mean()
        d = p[n : 2 * n] - p[n : 2 * n].mean()
        return np.asarray(a), np.asarray(d), p[2 * n], p[2 * n + 2]

    @property
    def rho(self) -> float:
        return float(self.params[2 * self._n + 1])

    def _strength(self, team: str, a, d):  # noqa: ANN001
        """(attack, defence) for a team — real if known, else the promoted-side prior."""
        if team in self.idx:
            i = self.idx[team]
            return float(a[i]), float(d[i])
        return self.PROMOTED_ATTACK, self.PROMOTED_DEFENCE

    def expected_goals(self, home: str, away: str) -> tuple[float, float]:
        import numpy as np  # noqa: PLC0415

        a, d, home_adv, mu = self._centred()
        att_h, def_h = self._strength(home, a, d)
        att_a, def_a = self._strength(away, a, d)
        lam_h = float(np.exp(mu + home_adv + att_h + def_a))
        lam_a = float(np.exp(mu + att_a + def_h))
        return lam_h, lam_a

    def predict(self, home: str, away: str) -> MatchProbabilities:
        lam_h, lam_a = self.expected_goals(home, away)
        return derive(lam_h, lam_a, self.rho)
