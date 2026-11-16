"""Minutes from a start-probability model (docs/MODEL_FIXES.md E6 and E9, HANDOFF §44).

WHAT PRODUCTION DOES. `MinutesModel.from_recent` averages the last six gameweeks' minutes, so a
player who played all six is certain to play (p_play 1.00). On players expected to play the model
runs high at every position (E9), and §19's oracle says knowing who starts is worth more than any
other fix (ρ 0.374 → 0.510 on 2023-26).

THE VARIANTS, everything else as production now is (k=3 rate blend, closing-odds lambdas, saves
2.02, defensive contribution by case, cards and assist factors):

  production    `from_recent` on the last six gameweeks
  start model   `models.starts.StartModel`: P(start), P(comes on), P(60+ | start) and minutes
                given a start, from the player's season-to-date starts and minutes

WHAT WAS LOOKED AT BEFORE THIS WAS WRITTEN (2026-11-16). On 2025-26: a first fit (C = 1, on
2023-25) against the heuristic, start Brier 0.075 against 0.092 and plays Brier 0.084 against
0.096, and their calibration where the heuristic is sure. On 2026-27: the cards retest's
descriptive line, which printed the bias by position on players expected to play (production
minutes); no minutes comparison has been run on 2026-27.

THE DECISION, WRITTEN BEFORE ANY RUN OF THIS TEST.

  Scored, per gameweek: squared error of total points over every player EITHER variant expected to
  play (p_play >= 0.5 before the deadline), whether or not he played: the same rows for both,
  chosen by the forecasts and not the result. Guard: the all-player played-only Spearman, as in
  every test. Reported, deciding nothing: the Spearman change with its interval (where §19 says
  the headroom is), the Brier score of p_play against appearing, and the bias by position.

  Development.
    1. For C in (0.1, 1, 10), fit on 2023-24 and 2024-25; choose the C with the lowest log-loss of
       P(start) on 2025-26.
    2. Score that fit against production on 2025-26. Go on only if the squared error is lower
       with a 95% interval below zero and the Spearman change has a 95% lower bound above -0.002.
       Otherwise stop: production stays.
    3. Refit with the chosen C on 2023-24, 2024-25 and 2025-26. That fit, saved to
       `models/start_model.json`, is the one held out and the one that would ship.

  Held out, 2026-27 GW2 onwards, run once (`compare_start_model.py --held-out`).
    SHIP           squared error lower with a 95% interval below zero, and the Spearman change has
                   a 95% lower bound above -0.002.
    DO NOT SHIP    squared error higher with a 95% interval above zero, or the Spearman change has
                   a 95% upper bound below zero.
    INCONCLUSIVE   anything else. Production stays.

Intervals are a bootstrap over whole gameweeks.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

C_GRID = (0.1, 1.0, 10.0)
EXPECTED_TO_PLAY = 0.5


def expected_rows(*p_plays: dict) -> set:
    """{(gw, element)} that any of the variants expected to play."""
    out: set = set()
    for pp in p_plays:
        out |= {k for k, p in pp.items() if p >= EXPECTED_TO_PLAY}
    return out


def plays_brier(p_play: dict, appeared: dict) -> float:
    """Brier score of p_play against appearing, over the (gw, element) both have."""
    keys = [k for k in p_play if k in appeared]
    return sum((p_play[k] - appeared[k]) ** 2 for k in keys) / len(keys)


def season_histories(rows: Iterable[dict]) -> dict:
    """{element: (position, [(minutes, starts) per gameweek, oldest first])} from per-fixture rows."""
    by: dict = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    pos: dict = {}
    for r in rows:
        g = by[r["element"]][r["gw"]]
        g[0] += r["minutes"]
        g[1] += r.get("starts", 0)
        pos[r["element"]] = r["position"]
    return {el: (pos[el], [tuple(gws[g]) for g in sorted(gws)]) for el, gws in by.items()}
