"""Squad optimiser — pick the best legal 15 under FPL constraints (PuLP ILP).

Constraints: £100.0m budget, exactly 2 GK / 5 DEF / 5 MID / 3 FWD, max 3 per club.
Objective (v1): maximise total xP. NOTE: for overall-RANK climbing you will later
swap the objective to expected rank vs the field, not raw xP (see xpoints docstring).

`pulp` is a declared dependency, imported lazily.
"""

from __future__ import annotations

from collections.abc import Sequence

SQUAD_QUOTA = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
MAX_PER_CLUB = 3
BUDGET = 100.0


def optimize_squad(players: Sequence[dict], budget: float = BUDGET) -> list[int]:
    """Return the element_ids of the optimal 15-man squad.

    Each player dict needs: element_id, position, price (in £m), team_id, xp.
    """
    import pulp  # noqa: PLC0415

    prob = pulp.LpProblem("fpl_squad", pulp.LpMaximize)
    pick = {p["element_id"]: pulp.LpVariable(f"pick_{p['element_id']}", cat="Binary") for p in players}

    # Objective: maximise expected points.
    prob += pulp.lpSum(pick[p["element_id"]] * p["xp"] for p in players)

    # Budget.
    prob += pulp.lpSum(pick[p["element_id"]] * p["price"] for p in players) <= budget

    # Positional quotas.
    for pos, n in SQUAD_QUOTA.items():
        prob += pulp.lpSum(pick[p["element_id"]] for p in players if p["position"] == pos) == n

    # Max 3 per club.
    for team_id in {p["team_id"] for p in players}:
        prob += pulp.lpSum(pick[p["element_id"]] for p in players if p["team_id"] == team_id) <= MAX_PER_CLUB

    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    return [eid for eid, var in pick.items() if var.value() == 1]
