"""Player goal/assist shares — how a team's expected goals are attributed to players.

Each player's share of their team's total last-season xG (and xA) becomes their share of
the team's expected goals this fixture. Because shares sum to 1 within a team, the sum of
player expected goals equals the team's lambda from the match engine — a coherent
attribution.

Honest caveat: last-season xG is a prior. New signings carry their previous club's output,
and promoted-team players have little/no top-flight history (cold start).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence


def team_shares(players: Sequence[dict]) -> dict:
    """Map player code -> {goal_share, assist_share} within their team_id.

    Each player dict needs: code, team_id, xg, xa.
    """
    team_xg: dict = defaultdict(float)
    team_xa: dict = defaultdict(float)
    for p in players:
        team_xg[p["team_id"]] += max(p.get("xg", 0.0), 0.0)
        team_xa[p["team_id"]] += max(p.get("xa", 0.0), 0.0)

    out: dict = {}
    for p in players:
        txg = team_xg[p["team_id"]]
        txa = team_xa[p["team_id"]]
        out[p["code"]] = {
            "goal_share": (max(p.get("xg", 0.0), 0.0) / txg) if txg > 0 else 0.0,
            "assist_share": (max(p.get("xa", 0.0), 0.0) / txa) if txa > 0 else 0.0,
        }
    return out


def team_minutes(players: Sequence[dict]) -> dict:
    """Sum of current-squad last-season minutes per team — a data-coverage signal.

    Low coverage (promoted / heavily-rebuilt squads) means the xG shares are unreliable.
    """
    tm: dict = defaultdict(float)
    for p in players:
        tm[p["team_id"]] += max(p.get("minutes", 0), 0)
    return dict(tm)


def match_shares(
    players: Sequence[dict], x_minutes_by_code: dict, min_season_minutes: int = 270
) -> dict:
    """Minutes-aware attribution: per-90 xG/xA rate x expected minutes, normalized per team.

    This is the correct distribution: a player's raw threat is his per-90 rate (a skill
    measure) times how much he is expected to play THIS match. Normalizing within the team
    keeps the sum equal to the engine's team lambda, and low-minute players no longer absorb
    a full-match share. Players with < `min_season_minutes` last season get a 0 rate (too
    small a sample to trust a per-90 estimate).
    """
    raw_g: dict = {}
    raw_a: dict = {}
    team_g: dict = defaultdict(float)
    team_a: dict = defaultdict(float)
    for p in players:
        mins = max(p["minutes"], 0)  # required: a missing key silently zeroed all shares before
        if mins >= min_season_minutes:
            per90 = mins / 90.0
            xg90 = max(p.get("xg", 0.0), 0.0) / per90
            xa90 = max(p.get("xa", 0.0), 0.0) / per90
        else:
            xg90 = xa90 = 0.0
        play = x_minutes_by_code.get(p["code"], 0.0) / 90.0
        raw_g[p["code"]] = xg90 * play
        raw_a[p["code"]] = xa90 * play
        team_g[p["team_id"]] += raw_g[p["code"]]
        team_a[p["team_id"]] += raw_a[p["code"]]

    out: dict = {}
    for p in players:
        g, a = team_g[p["team_id"]], team_a[p["team_id"]]
        out[p["code"]] = {
            "goal_share": raw_g[p["code"]] / g if g > 0 else 0.0,
            "assist_share": raw_a[p["code"]] / a if a > 0 else 0.0,
        }
    return out


def rate_shares(players: Sequence[dict], x_minutes_by_code: dict) -> dict:
    """Like `match_shares` but from pre-computed per-90 rates (`xg90`, `xa90`).

    Lets callers supply a recency-weighted (form) rate instead of a season average, while
    keeping the same minutes-aware, per-team-normalized attribution.
    """
    raw_g: dict = {}
    raw_a: dict = {}
    team_g: dict = defaultdict(float)
    team_a: dict = defaultdict(float)
    for p in players:
        play = x_minutes_by_code.get(p["code"], 0.0) / 90.0
        raw_g[p["code"]] = max(p.get("xg90", 0.0), 0.0) * play
        raw_a[p["code"]] = max(p.get("xa90", 0.0), 0.0) * play
        team_g[p["team_id"]] += raw_g[p["code"]]
        team_a[p["team_id"]] += raw_a[p["code"]]

    out: dict = {}
    for p in players:
        g, a = team_g[p["team_id"]], team_a[p["team_id"]]
        out[p["code"]] = {
            "goal_share": raw_g[p["code"]] / g if g > 0 else 0.0,
            "assist_share": raw_a[p["code"]] / a if a > 0 else 0.0,
        }
    return out
