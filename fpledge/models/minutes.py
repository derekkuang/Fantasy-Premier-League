"""Minutes / start-probability model — the highest-leverage FPL sub-model.

xP is dominated by whether a player clears the 60-minute threshold, so rotation and
return-from-injury timing matter more than goal-share precision. This is a baseline
HEURISTIC; Phase 4 replaces it with a trained classifier (LightGBM) on recent
minutes, price, position, FPL `chance_of_playing`, and press-conference signals.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


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
