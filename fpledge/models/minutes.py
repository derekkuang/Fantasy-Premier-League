"""Minutes / start-probability model — the highest-leverage FPL sub-model.

xP is dominated by whether a player clears the 60-minute threshold, so rotation and
return-from-injury timing matter more than goal-share precision. This is a baseline
HEURISTIC; Phase 4 replaces it with a trained classifier (LightGBM) on recent
minutes, price, position, FPL `chance_of_playing`, and press-conference signals.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

# FPL availability status codes that mean "won't feature": injured, suspended,
# unavailable, not-in-squad. ('a' = available, 'd' = doubtful -> use chance_of_playing.)
_OUT_STATUSES = {"i", "s", "u", "n", "o"}

# Gameweeks the recency model reads (`from_recent(recent[-RECENT_GWS:])`). One definition:
# the validation harness and the serving path must score the SAME window, or the shipped
# model quietly diverges from the measured one — the gap that motivated wiring recency
# minutes into serving in the first place.
RECENT_GWS = 6


@dataclass
class MinutesPrediction:
    p_play: float   # P(minutes > 0)
    p_60: float     # P(minutes >= 60)
    x_minutes: float


class MinutesModel:
    """Baseline: blends recent minutes with FPL's chance-of-playing flag."""

    def predict(
        self, recent_minutes: Sequence[int], chance_of_playing: float | None = None
    ) -> MinutesPrediction:
        """`chance_of_playing` is FPL's 0–100 field (None = no news = assume fit)."""
        avail = 1.0 if chance_of_playing is None else max(0.0, min(chance_of_playing, 100.0)) / 100.0

        if not recent_minutes:
            # No history: lean on availability only, assume nailed-ish if fit.
            return MinutesPrediction(p_play=avail, p_60=0.6 * avail, x_minutes=60.0 * avail)

        window = list(recent_minutes)[-5:]
        avg_min = sum(window) / len(window)
        start_rate = sum(1 for m in window if m >= 60) / len(window)

        p_play = avail * min(1.0, 0.2 + start_rate + (0.2 if avg_min > 0 else 0.0))
        p_60 = avail * start_rate
        x_minutes = avail * avg_min
        return MinutesPrediction(
            p_play=min(p_play, 1.0), p_60=min(p_60, 1.0), x_minutes=x_minutes
        )

    def from_season(
        self, minutes: int, starts: int, games: int = 38
    ) -> MinutesPrediction:
        """Preseason proxy from last-season totals (no per-game history yet).

        p_60 ~ start rate; p_play adds a sub allowance; x_minutes = minutes/games.
        """
        if games <= 0:
            return MinutesPrediction(p_play=0.0, p_60=0.0, x_minutes=0.0)
        p_60 = min(starts / games, 1.0)
        p_play = min(p_60 + 0.15, 1.0) if minutes > 0 else 0.0
        return MinutesPrediction(p_play=p_play, p_60=p_60, x_minutes=minutes / games)

    def from_recent(
        self, recent_minutes, chance_of_playing: float | None = None, half_life: float = 3.0
    ) -> MinutesPrediction:
        """Recency-weighted minutes from a list of recent GWs' minutes (oldest -> newest).

        Recent gameweeks are weighted more (exponential, `half_life` in GWs), so a player who
        was just dropped/injured or has just nailed a starting spot is scored on current
        reality, not a diluted season average. `chance_of_playing` (FPL 0-100), when known,
        scales the result.
        """
        recent = list(recent_minutes)
        if not recent:
            return MinutesPrediction(0.0, 0.0, 0.0)
        n = len(recent)
        w = [0.5 ** ((n - 1 - i) / half_life) for i in range(n)]  # newest weight 1
        total = sum(w)
        x_minutes = min(sum(wi * m for wi, m in zip(w, recent, strict=True)) / total, 90.0)
        p_60 = sum(wi for wi, m in zip(w, recent, strict=True) if m >= 60) / total
        p_play = sum(wi for wi, m in zip(w, recent, strict=True) if m > 0) / total
        avail = 1.0 if chance_of_playing is None else max(0.0, min(chance_of_playing, 100.0)) / 100.0
        return MinutesPrediction(p_play=p_play * avail, p_60=p_60 * avail, x_minutes=x_minutes * avail)

    def apply_availability(
        self, pred: MinutesPrediction, chance_of_playing: float | None = None, status: str | None = None
    ) -> MinutesPrediction:
        """Scale a minutes prediction by live FPL availability (production path)."""
        factor = availability_factor(chance_of_playing, status)
        return MinutesPrediction(pred.p_play * factor, pred.p_60 * factor, pred.x_minutes * factor)


def availability_factor(
    chance_of_playing: float | None = None, status: str | None = None
) -> float:
    """The multiplier live FPL availability applies to a minutes prediction.

    status in {i,s,u,n,o} -> won't feature (0.0); 'd'/None with a chance_of_playing -> that
    fraction; otherwise 1.0. Exposed separately from `apply_availability` because the serving
    layer surfaces it: a player showing 0.00 xP needs to say WHY, and "75% chance to play"
    is the whole explanation for a quietly discounted projection.
    """
    if status in _OUT_STATUSES:
        return 0.0
    if chance_of_playing is not None:
        return max(0.0, min(chance_of_playing, 100.0)) / 100.0
    return 1.0
