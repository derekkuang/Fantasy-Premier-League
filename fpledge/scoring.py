"""FPL points scoring — 2025/26 rules, including the new Defensive Contribution.

Stdlib-only and deterministic: given a player's match stat line, return the FPL
points. Used to build ground-truth labels for the backtest and to sanity-check
expected-points (xP) assembly. Constants live in `config` so a rules change is a
one-line edit.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import config


@dataclass
class StatLine:
    """A single player's stats for a single match."""

    position: str          # "GK" | "DEF" | "MID" | "FWD"
    minutes: int = 0
    goals: int = 0
    assists: int = 0
    goals_conceded: int = 0
    saves: int = 0
    penalties_saved: int = 0
    penalties_missed: int = 0
    yellow_cards: int = 0
    red_cards: int = 0
    own_goals: int = 0
    bonus: int = 0
    # Defensive-action tallies for the 2025/26 Defensive Contribution point:
    cbit: int = 0          # clearances + blocks + interceptions + tackles
    recoveries: int = 0    # ball recoveries (counts for MID/FWD only)

    @property
    def clean_sheet(self) -> bool:
        # A clean sheet requires 60+ minutes AND zero conceded while on the pitch.
        # We approximate "while on the pitch" with the match total (adequate for
        # a scaffold; refine with minute-level data later).
        return self.minutes >= 60 and self.goals_conceded == 0


def defensive_contribution_points(position: str, cbit: int, recoveries: int) -> int:
    """The 2025/26 DC point (+2, capped once per match)."""
    if position == "DEF":
        return config.DC_POINTS if cbit >= config.DC_THRESHOLD_DEF else 0
    if position in ("MID", "FWD"):
        total = cbit + recoveries  # CBIRT
        return config.DC_POINTS if total >= config.DC_THRESHOLD_MID_FWD else 0
    return 0  # GK has no defensive-contribution category


def total_points(s: StatLine) -> int:
    """Total FPL points for a stat line under the 2025/26 rules."""
    pos = s.position
    pts = 0

    # Appearance
    if s.minutes >= 60:
        pts += config.APPEARANCE_60_POINTS
    elif s.minutes > 0:
        pts += config.APPEARANCE_SUB_POINTS

    # Attacking returns
    pts += s.goals * config.GOAL_POINTS[pos]
    pts += s.assists * config.ASSIST_POINTS

    # Clean sheet (only if 60+ minutes)
    if s.clean_sheet:
        pts += config.CLEAN_SHEET_POINTS[pos]

    # Goals conceded (GK/DEF): -1 per 2 conceded
    if pos in ("GK", "DEF"):
        pts -= s.goals_conceded // config.GOALS_CONCEDED_PER_PENALTY

    # Goalkeeping
    if pos == "GK":
        pts += s.saves // config.SAVES_PER_POINT
    pts += s.penalties_saved * config.PENALTY_SAVE_POINTS

    # Penalties / cards / own goals
    pts += s.penalties_missed * config.PENALTY_MISS_POINTS
    pts += s.yellow_cards * config.YELLOW_CARD_POINTS
    pts += s.red_cards * config.RED_CARD_POINTS
    pts += s.own_goals * config.OWN_GOAL_POINTS

    # Bonus
    pts += s.bonus

    # NEW 2025/26 — Defensive Contribution
    pts += defensive_contribution_points(pos, s.cbit, s.recoveries)

    return pts
