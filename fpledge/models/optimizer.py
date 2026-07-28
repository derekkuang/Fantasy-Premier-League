"""Squad optimiser — the best legal FPL squad AND starting XI + captain (one ILP).

Two coupled decisions, one integer program:
  * pick a 15-man SQUAD (2 GK / 5 DEF / 5 MID / 3 FWD, <= £budget, <= 3 per club);
  * pick the 11 that START (valid formation) and the CAPTAIN (doubled).
Only the XI scores in FPL, so the objective maximises XI xP + captain xP (the extra
captain point); the four benched players are whatever cheap/low-xP fillers legally
complete the 15 without helping the objective.

`pulp` is a declared dependency, imported lazily.
"""

from __future__ import annotations

from collections.abc import Sequence

SQUAD_QUOTA = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
FORMATION = {"GK": (1, 1), "DEF": (3, 5), "MID": (2, 5), "FWD": (1, 3)}  # (min, max) in the XI
MAX_PER_CLUB = 3
BUDGET = 100.0
SQUAD_SIZE = 15
XI_SIZE = 11


def best_xi(players: Sequence[dict]) -> dict | None:
    """Best legal starting XI + captain from a FIXED 15-man squad (no ILP needed).

    Enumerates valid formations (1 GK; DEF 3-5, MID 2-5, FWD 1-3) and takes the top xP per
    position. Each player dict needs id, position, xp. Returns {xi, captain, xi_xp, total_xp}
    (captain counted twice), or None if the squad can't field a legal XI.
    """
    by_pos = {
        pos: sorted((p for p in players if p["position"] == pos), key=lambda p: p["xp"], reverse=True)
        for pos in ("GK", "DEF", "MID", "FWD")
    }
    if not by_pos["GK"]:
        return None
    best = None
    for d in range(3, 6):
        for m in range(2, 6):
            f = 10 - d - m
            if not (1 <= f <= 3):
                continue
            if len(by_pos["DEF"]) < d or len(by_pos["MID"]) < m or len(by_pos["FWD"]) < f:
                continue
            xi = by_pos["GK"][:1] + by_pos["DEF"][:d] + by_pos["MID"][:m] + by_pos["FWD"][:f]
            xp = sum(p["xp"] for p in xi)
            if best is None or xp > best[0]:
                best = (xp, xi)
    if best is None:
        return None
    xi_xp, xi = best
    captain = max(xi, key=lambda p: p["xp"])
    return {
        "xi": [p["id"] for p in xi],
        "captain": captain["id"],
        "xi_xp": xi_xp,
        "total_xp": xi_xp + captain["xp"],
    }


def optimize_squad(players: Sequence[dict], budget: float = BUDGET) -> dict:
    """Return the optimal squad/XI/captain.

    Each player dict needs: id (unique), position, price, team_id, xp.
    Returns {squad, starting_xi, bench, captain, cost, xi_xp, total_xp}.
    Raises ValueError if no feasible optimal squad exists (pool too small / budget too tight).
    """
    import pulp  # noqa: PLC0415

    by_id = {p["id"]: p for p in players}
    ids = list(by_id)

    prob = pulp.LpProblem("fpl_squad", pulp.LpMaximize)
    in_squad = pulp.LpVariable.dicts("squad", ids, cat="Binary")
    in_xi = pulp.LpVariable.dicts("xi", ids, cat="Binary")
    is_cap = pulp.LpVariable.dicts("cap", ids, cat="Binary")

    # Objective: starting-XI xP, plus the captain's xP again (doubling).
    prob += (
        pulp.lpSum(in_xi[i] * by_id[i]["xp"] for i in ids)
        + pulp.lpSum(is_cap[i] * by_id[i]["xp"] for i in ids)
    )

    # Linking: you can only start a squad member; only captain a starter.
    for i in ids:
        prob += in_xi[i] <= in_squad[i]
        prob += is_cap[i] <= in_xi[i]

    prob += pulp.lpSum(in_squad[i] for i in ids) == SQUAD_SIZE
    prob += pulp.lpSum(in_xi[i] for i in ids) == XI_SIZE
    prob += pulp.lpSum(is_cap[i] for i in ids) == 1

    # Squad quotas (all 15).
    for pos, n in SQUAD_QUOTA.items():
        prob += pulp.lpSum(in_squad[i] for i in ids if by_id[i]["position"] == pos) == n

    # Formation bounds (the XI).
    for pos, (lo, hi) in FORMATION.items():
        count = pulp.lpSum(in_xi[i] for i in ids if by_id[i]["position"] == pos)
        prob += count >= lo
        prob += count <= hi

    # Budget (all 15 count) and max 3 per club.
    prob += pulp.lpSum(in_squad[i] * by_id[i]["price"] for i in ids) <= budget
    for team in {by_id[i]["team_id"] for i in ids}:
        prob += pulp.lpSum(in_squad[i] for i in ids if by_id[i]["team_id"] == team) <= MAX_PER_CLUB

    status = prob.solve(pulp.PULP_CBC_CMD(msg=False))
    if pulp.LpStatus[status] != "Optimal":
        raise ValueError(
            f"no optimal squad (status={pulp.LpStatus[status]}); "
            "pool too small, budget too tight, or too few clubs."
        )

    def chosen(var) -> list:  # noqa: ANN001
        return [i for i in ids if (var[i].value() or 0) > 0.5]

    squad = chosen(in_squad)
    xi = set(chosen(in_xi))
    captain = chosen(is_cap)[0]
    starting_xi = [i for i in squad if i in xi]
    bench = [i for i in squad if i not in xi]
    cost = sum(by_id[i]["price"] for i in squad)
    xi_xp = sum(by_id[i]["xp"] for i in xi)
    return {
        "squad": squad,
        "starting_xi": starting_xi,
        "bench": bench,
        "captain": captain,
        "cost": cost,
        "xi_xp": xi_xp,
        "total_xp": xi_xp + by_id[captain]["xp"],  # captain counted twice
    }
