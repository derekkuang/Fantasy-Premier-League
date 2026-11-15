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

import math
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
    x_bonus: float = 0.0   # expected bonus points
    opp_lambda: float = 0.0  # opponent expected goals (for the goals-conceded penalty)
    x_conceded_penalty: float = 0.0  # expected goals-conceded points (<= 0), GK/DEF only
    # Expected save points, when the caller computed them with FPL's per-match rounding
    # (`expected_save_points`). None keeps the old linear x_saves / 3.
    x_save_points: float | None = None


def expected_points_breakdown(ctx: PlayerContext) -> dict:
    """The xP equation decomposed into its per-term point contributions.

    Each `*_points` term is the mean points from that scoring category; they sum to
    `total`, which equals `expected_points(ctx)`. Also returns the underlying expected
    quantities (x_goals, x_assists, probabilities) so the model can be shown transparently.
    """
    pos = ctx.position

    # Appearance (2 for 60+, 1 for 1–59)
    appearance = (
        ctx.p_60 * config.APPEARANCE_60_POINTS
        + max(ctx.p_play - ctx.p_60, 0.0) * config.APPEARANCE_SUB_POINTS
    )
    # Attacking returns
    x_goals = ctx.goal_share * ctx.team_lambda
    x_assists = ctx.assist_share * ctx.team_lambda
    goal_points = x_goals * config.GOAL_POINTS[pos]
    assist_points = x_assists * config.ASSIST_POINTS
    # Clean sheet (only counts with 60+ minutes)
    cs_points = ctx.p_clean_sheet * ctx.p_60 * config.CLEAN_SHEET_POINTS[pos]
    # Goals conceded: GK/DEF lose 1 point per 2 conceded while on the pitch (not 60-gated).
    conceded_points = ctx.x_conceded_penalty if pos in ("GK", "DEF") else 0.0
    # Goalkeeping saves (1 point per 3 in a match)
    if pos != "GK":
        save_points = 0.0
    elif ctx.x_save_points is not None:
        save_points = ctx.x_save_points
    else:
        save_points = ctx.x_saves / config.SAVES_PER_POINT
    # 2025/26 Defensive Contribution (+2 if threshold hit)
    dc_points = ctx.p_dc_point * config.DC_POINTS
    # Expected bonus points
    bonus_points = ctx.x_bonus

    total = (
        appearance + goal_points + assist_points + cs_points + conceded_points
        + save_points + dc_points + bonus_points
    )
    return {
        # expected quantities (for display)
        "p_play": ctx.p_play, "p_60": ctx.p_60,
        "x_goals": x_goals, "x_assists": x_assists,
        "p_clean_sheet": ctx.p_clean_sheet, "x_saves": ctx.x_saves,
        "p_dc_point": ctx.p_dc_point, "opp_lambda": ctx.opp_lambda,
        # point contributions (sum to total)
        "appearance": appearance, "goal_points": goal_points, "assist_points": assist_points,
        "cs_points": cs_points, "conceded_points": conceded_points,
        "save_points": save_points, "dc_points": dc_points, "bonus_points": bonus_points,
        "total": total,
    }


def expected_points(ctx: PlayerContext) -> float:
    """Mean expected FPL points for one player in one fixture (sum of the term breakdown)."""
    return expected_points_breakdown(ctx)["total"]


def _poisson_sf(k: int, lam: float) -> float:
    """Survival function P(X >= k) for X ~ Poisson(lam), stdlib-only."""
    if lam <= 0:
        return 1.0 if k <= 0 else 0.0
    cdf = 0.0
    term = math.exp(-lam)  # P(X = 0)
    for i in range(k):
        cdf += term
        term *= lam / (i + 1)
    return max(0.0, 1.0 - cdf)


def dc_point_probability(dc_per90: float, x_minutes: float, position: str) -> float:
    """P(a player hits the 2025/26 defensive-contribution threshold this match).

    Models the per-match defensive-action count as Poisson(mean = per-90 rate x minutes/90)
    and returns the tail above the position threshold (DEF 10 CBIT; MID/FWD 12 CBIRT).
    GKs have no DC category -> 0.

    Caveat: real defensive-action counts are mildly OVERDISPERSED (variance > mean) and
    game-state dependent, so Poisson slightly understates the tail for busy defenders. A
    negative-binomial refinement is future work; Poisson is an acceptable first cut.
    """
    if position == "DEF":
        threshold = config.DC_THRESHOLD_DEF
    elif position in ("MID", "FWD"):
        threshold = config.DC_THRESHOLD_MID_FWD
    else:
        return 0.0
    expected_actions = max(dc_per90, 0.0) * (x_minutes / 90.0)
    return _poisson_sf(threshold, expected_actions)


def _nbinom_sf(k: int, mean: float, size: float) -> float:
    """P(X >= k) for a negative binomial with this mean and size (variance = mean + mean^2/size)."""
    if mean <= 0:
        return 1.0 if k <= 0 else 0.0
    p = size / (size + mean)
    term = p ** size  # P(X = 0)
    cdf = 0.0
    for i in range(k):
        cdf += term
        term *= (i + size) / (i + 1) * (1.0 - p)
    return max(0.0, 1.0 - cdf)


def dc_point_probability_by_case(
    dc_per90: float, p_play: float, p_60: float, x_minutes: float, position: str,
    sub_minutes: float = config.SUB_APPEARANCE_MINUTES, size: float | None = None,
) -> float:
    """P(a player hits the defensive-contribution threshold), taken case by case.

    `dc_point_probability` applies the tail to the mean at EXPECTED minutes, which already
    include the chance he does not play. The tail is steep, so that crushes a rotation player:
    a defender averaging 9 a full game reaches 10 about 41% of the time, but at 60% of that mean
    about 5%, where the right answer is 60% x 41% (HANDOFF §42). Here the minutes prediction is
    split into "plays 60+" (`p_60`, at the minutes that leaves) and "comes on" (`p_play - p_60`,
    at `sub_minutes`), the tail is taken in each, and the cases are weighted. `size` switches the
    Poisson tail for a negative binomial.
    """
    if position == "DEF":
        threshold = config.DC_THRESHOLD_DEF
    elif position in ("MID", "FWD"):
        threshold = config.DC_THRESHOLD_MID_FWD
    else:
        return 0.0
    rate = max(dc_per90, 0.0) / 90.0

    def tail(mean: float) -> float:
        return _poisson_sf(threshold, mean) if size is None else _nbinom_sf(threshold, mean, size)

    p_sub = max(p_play - p_60, 0.0)
    out = p_sub * tail(rate * sub_minutes)
    if p_60 > 0:
        full = min(max((x_minutes - p_sub * sub_minutes) / p_60, 60.0), 90.0)
        out += p_60 * tail(rate * full)
    return min(out, 1.0)


def expected_conceded_penalty(opp_lambda: float, x_minutes: float, max_terms: int = 6) -> float:
    """Expected goals-conceded points for a GK/DEF (<= 0), from the opponent's goal distribution.

    FPL docks GK/DEF 1 point per 2 goals their team concedes WHILE THEY ARE ON THE PITCH.
    With conceded C ~ Poisson(opp_lambda), the penalty count is floor(C / per), whose mean is
    sum_{k>=1} P(C >= per*k). Scaled by expected on-pitch time (x_minutes/90) since only goals
    conceded while playing count. Not 60-gated (unlike the clean-sheet bonus).
    """
    per = config.GOALS_CONCEDED_PER_PENALTY  # 2 conceded -> -1 point
    frac = max(0.0, min(x_minutes / 90.0, 1.0))
    e_units = sum(_poisson_sf(per * k, max(opp_lambda, 0.0)) for k in range(1, max_terms + 1))
    return -e_units * frac


def expected_save_points(x_saves: float, x_minutes: float, max_terms: int = 10) -> float:
    """Expected save points for a keeper, with FPL's rounding.

    FPL pays 1 point per 3 saves IN A MATCH, rounded down, so two saves earn nothing. With the
    match's saves S ~ Poisson(m), the points are floor(S / 3), whose mean is
    sum_{k>=1} P(S >= 3k): the same construction as `expected_conceded_penalty`. `x_saves` is
    already scaled by expected time on the pitch, so m = x_saves / (x_minutes / 90) and the
    result is scaled back. x_saves / 3 ignores the rounding and overstates a keeper who makes
    about three saves a game by roughly half (HANDOFF §41).
    """
    per = config.SAVES_PER_POINT
    frac = max(0.0, min(x_minutes / 90.0, 1.0))
    if frac <= 0.0 or x_saves <= 0.0:
        return 0.0
    m = x_saves / frac
    return frac * sum(_poisson_sf(per * k, m) for k in range(1, max_terms + 1))


def expected_bonus(bonus_per90: float, x_minutes: float) -> float:
    """Expected bonus from a last-season per-90 bonus rate scaled by expected minutes."""
    return max(bonus_per90, 0.0) * (x_minutes / 90.0)


def bonus_from_returns(x_goals: float, x_assists: float, cs_prob: float, p_dc: float) -> float:
    """Expected bonus tied to THIS fixture's expected returns, not a stale season rate.

    Bonus (BPS top-3) is driven by performance: scorers and returners collect it. These are
    rough BPS-derived priors (a goal is worth ~1.5 expected bonus on average, an assist ~0.8,
    a clean sheet ~0.5, a defensive-contribution point ~0.3), capped at the 3-point maximum.
    """
    b = 1.5 * x_goals + 0.8 * x_assists + 0.5 * cs_prob + 0.3 * p_dc
    return min(b, 3.0)
