"""Expected points (xP) assembly — pure expected value off the shared engine.

xP = f(minutes, team goal expectation, player goal/assist share, clean-sheet prob,
       saves, defensive-contribution prob). No ML needed for a first cut; the match
engine and player shares supply everything. LightGBM later improves the *shares*
and the minutes model — not this assembly.

IMPORTANT (rank vs points): raw-xP maximisation is NOT rank maximisation in FPL.
Captaincy and differential decisions should optimise expected RANK against the
field (effective ownership), not raw xP. That objective lives in `optimizer`/a
future `rank` module; this file computes the honest per-player mean xP it needs.
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import config


@dataclass
class PlayerContext:
    position: str          # GK | DEF | MID | FWD
    p_play: float          # P(minutes > 0)
    p_60: float            # P(minutes >= 60)
    team_lambda: float     # team expected goals for this fixture (from engine)
    goal_share: float      # player's share of team goals (xG-based)
    assist_share: float    # player's share of team assists
    p_clean_sheet: float   # from the match engine
    x_saves: float = 0.0   # expected saves (GK), = f(opponent lambda)
    p_dc_point: float = 0.0  # P(hitting the 2025/26 defensive-contribution threshold)


def expected_points(ctx: PlayerContext) -> float:
    """Mean expected FPL points for one player in one fixture."""
    pos = ctx.position
    xp = 0.0

    # Appearance (2 for 60+, 1 for 1–59)
    xp += ctx.p_60 * config.APPEARANCE_60_POINTS
    xp += max(ctx.p_play - ctx.p_60, 0.0) * config.APPEARANCE_SUB_POINTS

    # Attacking returns
    x_goals = ctx.goal_share * ctx.team_lambda
    x_assists = ctx.assist_share * ctx.team_lambda
    xp += x_goals * config.GOAL_POINTS[pos]
    xp += x_assists * config.ASSIST_POINTS

    # Clean sheet (only counts with 60+ minutes)
    xp += ctx.p_clean_sheet * ctx.p_60 * config.CLEAN_SHEET_POINTS[pos]

    # Goalkeeping saves (1 point per 3)
    if pos == "GK":
        xp += ctx.x_saves / config.SAVES_PER_POINT

    # 2025/26 Defensive Contribution (+2 if threshold hit)
    xp += ctx.p_dc_point * config.DC_POINTS

    return xp
