"""Start-probability minutes model (docs/MODEL_FIXES.md E6, HANDOFF §44).

`MinutesModel.from_recent` averages the last six gameweeks, so a player who played all six is
"certain" to play: p_play 1.00. On 2025-26 those players played 90% of the time and reached 60
minutes 87% of the time, and that overconfidence on the most-picked players is why projections
ran high for everyone expected to play (E9). This model learns, from past seasons, how a
player's recent starts and minutes translate into the next match:

    P(start)                 logistic on the features below
    P(comes on | no start)   logistic, same features
    P(60+ | start)           logistic, same features
    minutes | start          linear, same features, clamped to 45-90
    minutes | comes on       a constant, the training seasons' average

combined into the same `MinutesPrediction` production already uses:

    p_play    = Ps + (1 - Ps) x Psub
    p_60      = Ps x P60
    x_minutes = Ps x Mstart + (1 - Ps) x Psub x Msub

Inference is plain arithmetic on stored coefficients (`start_model.json`), so serving needs no
model library. Fitting (`fit`) uses scikit-learn and runs offline only.

A player's history is one (minutes, starts) pair per gameweek his club played, oldest first, this
season only. A double gameweek is clipped to one match's worth (90 minutes, 1 start), which is
what the training rows look like.
"""

from __future__ import annotations

import json
import math
import pathlib
from collections.abc import Sequence
from dataclasses import dataclass

from .minutes import MinutesPrediction

MODEL_PATH = pathlib.Path(__file__).with_name("start_model.json")
CAP = 10            # gameweeks; "since last start" and "since last appearance" stop counting here
POSITIONS = ("GK", "DEF", "MID", "FWD")
FEATURES = (
    "started last", "starts of last 3", "starts of last 5", "appearances of last 5",
    "minutes last", "minutes of last 3", "since last start", "since last appearance",
    "season start rate", "log matches", "minutes when starting", "DEF", "MID", "FWD",
)


def clip_gw(minutes: int, starts: int) -> tuple[int, int]:
    """One gameweek as one match: a double gameweek's 180 minutes and 2 starts count once."""
    return min(int(minutes), 90), min(int(starts), 1)


def features(history: Sequence[tuple[int, int]], position: str) -> list[float]:
    """The feature vector from a player's earlier gameweeks this season, oldest first. Needs one."""
    mins = [m for m, _s in history]
    st = [s for _m, s in history]
    n = len(history)

    def rate(xs: list, k: int) -> float:
        xs = xs[-k:]
        return sum(xs) / len(xs)

    def since(flags: list) -> int:
        for i, f in enumerate(reversed(flags)):
            if f:
                return i
        return CAP

    played = [m > 0 for m in mins]
    starting = [m for m, s in zip(mins, st, strict=True) if s][-5:]
    return [
        float(st[-1]), rate(st, 3), rate(st, 5), rate(played, 5),
        mins[-1] / 90.0, rate(mins, 3) / 90.0,
        min(since(st), CAP) / CAP, min(since(played), CAP) / CAP,
        sum(st) / n, math.log1p(n),
        (sum(starting) / len(starting) / 90.0) if starting else 0.0,
        *[1.0 if position == p else 0.0 for p in POSITIONS[1:]],
    ]


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z)) if z >= 0 else math.exp(z) / (1.0 + math.exp(z))


@dataclass
class StartModel:
    start: tuple[float, list[float]]          # (intercept, coefficients) per part
    sub: tuple[float, list[float]]
    sixty: tuple[float, list[float]]
    minutes: tuple[float, list[float]]
    sub_minutes: float
    trained_on: list[str]
    c: float

    def _lin(self, part: tuple[float, list[float]], x: list[float]) -> float:
        b, w = part
        return b + sum(wi * xi for wi, xi in zip(w, x, strict=True))

    def predict(self, history: Sequence[tuple[int, int]], position: str) -> MinutesPrediction:
        if not history:
            return MinutesPrediction(0.0, 0.0, 0.0)
        x = features([clip_gw(m, s) for m, s in history], position)
        ps = _sigmoid(self._lin(self.start, x))
        psub = _sigmoid(self._lin(self.sub, x))
        p60 = _sigmoid(self._lin(self.sixty, x))
        mstart = min(max(self._lin(self.minutes, x), 45.0), 90.0)
        p_play = ps + (1.0 - ps) * psub
        return MinutesPrediction(
            p_play=p_play, p_60=ps * p60,
            x_minutes=ps * mstart + (1.0 - ps) * psub * self.sub_minutes,
        )

    def to_json(self) -> dict:
        return {"start": self.start, "sub": self.sub, "sixty": self.sixty, "minutes": self.minutes,
                "sub_minutes": self.sub_minutes, "trained_on": self.trained_on, "c": self.c,
                "features": list(FEATURES)}

    @classmethod
    def from_json(cls, d: dict) -> StartModel:
        if d.get("features") != list(FEATURES):
            raise ValueError("start_model.json was fitted on a different feature list")
        return cls(start=tuple(d["start"]), sub=tuple(d["sub"]), sixty=tuple(d["sixty"]),
                   minutes=tuple(d["minutes"]), sub_minutes=d["sub_minutes"],
                   trained_on=d["trained_on"], c=d["c"])


def load(path: pathlib.Path = MODEL_PATH) -> StartModel:
    return StartModel.from_json(json.loads(path.read_text()))


def training_rows(histories: dict) -> list[tuple[list[float], int, int, int, int]]:
    """(features, started, appeared, sixty, minutes) for every gameweek after a player's first.

    `histories` is {player: (position, [(minutes, starts), ...])} for one season, every gameweek
    his club played, oldest first."""
    out = []
    for position, hist in histories.values():
        hist = [clip_gw(m, s) for m, s in hist]
        for i in range(1, len(hist)):
            m, s = hist[i]
            out.append((features(hist[:i], position), s, int(m > 0), int(m >= 60), m))
    return out


def fit(rows: Sequence[tuple], seasons: list[str], c: float = 1.0) -> StartModel:
    """Fit the four parts on `training_rows` output. Offline only (scikit-learn)."""
    import numpy as np
    from sklearn.linear_model import LinearRegression, LogisticRegression

    X = np.array([r[0] for r in rows])
    started, appeared, sixty, minutes = (np.array([r[i] for r in rows]) for i in (1, 2, 3, 4))

    def logit(mask, y) -> tuple[float, list[float]]:
        m = LogisticRegression(C=c, max_iter=5000).fit(X[mask], y[mask])
        return float(m.intercept_[0]), [float(v) for v in m.coef_[0]]

    s = started == 1
    lin = LinearRegression().fit(X[s], minutes[s])
    on = (started == 0) & (appeared == 1)
    return StartModel(
        start=logit(np.ones(len(X), bool), started),
        sub=logit(started == 0, appeared),
        sixty=logit(s, sixty),
        minutes=(float(lin.intercept_), [float(v) for v in lin.coef_]),
        sub_minutes=float(minutes[on].mean()),
        trained_on=list(seasons), c=c,
    )
