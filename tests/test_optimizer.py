"""Squad optimiser: the returned squad + XI + captain must be legal and optimal.

Skipped when pulp isn't installed, so the stdlib-only core still runs with just pytest.
"""

from collections import Counter

import pytest

pytest.importorskip("pulp")

from fpledge.models.optimizer import FORMATION, SQUAD_QUOTA, optimize_squad  # noqa: E402


def _pool():
    # 3 GK / 8 DEF / 8 MID / 5 FWD across 8 clubs (<=3 per club feasible), £5.0 each.
    players, pid = [], 0
    for pos, n in [("GK", 3), ("DEF", 8), ("MID", 8), ("FWD", 5)]:
        for _ in range(n):
            players.append(
                {"id": pid, "position": pos, "price": 5.0, "team_id": pid % 8, "xp": 1.0 + (pid % 7) * 0.5}
            )
            pid += 1
    return players


def test_optimize_returns_a_legal_optimal_squad():
    pool = _pool()
    by_id = {p["id"]: p for p in pool}
    res = optimize_squad(pool, budget=100.0)

    assert len(res["squad"]) == 15
    assert Counter(by_id[i]["position"] for i in res["squad"]) == Counter(SQUAD_QUOTA)

    assert len(res["starting_xi"]) == 11
    assert len(res["bench"]) == 4
    xi_pos = Counter(by_id[i]["position"] for i in res["starting_xi"])
    for pos, (lo, hi) in FORMATION.items():
        assert lo <= xi_pos.get(pos, 0) <= hi

    # captain starts and is the highest-xP starter (doubling makes that optimal)
    assert res["captain"] in res["starting_xi"]
    assert by_id[res["captain"]]["xp"] == max(by_id[i]["xp"] for i in res["starting_xi"])

    assert res["cost"] <= 100.0 + 1e-9
    assert abs(res["total_xp"] - (res["xi_xp"] + by_id[res["captain"]]["xp"])) < 1e-9


def test_max_three_per_club_enforced():
    pool = _pool()
    by_id = {p["id"]: p for p in pool}
    res = optimize_squad(pool, budget=100.0)
    per_club = Counter(by_id[i]["team_id"] for i in res["squad"])
    assert max(per_club.values()) <= 3


def test_infeasible_budget_raises():
    pool = [
        {"id": i, "position": pos, "price": 50.0, "team_id": i % 8, "xp": 1.0}
        for i, pos in enumerate(
            ["GK", "GK", "DEF", "DEF", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "MID", "FWD", "FWD", "FWD"]
        )
    ]
    with pytest.raises(ValueError):  # 15 x £50 = £750 >> £100
        optimize_squad(pool, budget=100.0)
