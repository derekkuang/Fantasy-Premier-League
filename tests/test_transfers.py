"""Transfer suggester: best_xi legality, that an upgrade is found, and the -4 hit accounting."""

from fpledge.models.optimizer import best_xi
from fpledge.transfers import suggest_transfers


def _pool():
    players, pid = [], 0
    for pos, n in [("GK", 2), ("DEF", 5), ("MID", 5), ("FWD", 3)]:
        for _ in range(n):
            players.append(
                {"id": pid, "name": f"{pos}{pid}", "position": pos, "price": 5.0,
                 "team_id": pid % 6, "team_name": f"T{pid % 6}", "xp": 3.0}
            )
            pid += 1
    owned = [p["id"] for p in players]
    star = {"id": 100, "name": "Star", "position": "MID", "price": 5.0,
            "team_id": 6, "team_name": "T6", "xp": 8.0}  # a clearly better, affordable spare
    players.append(star)
    return owned, {p["id"]: p for p in players}


def test_best_xi_is_legal():
    owned, by_id = _pool()
    xi = best_xi([by_id[i] for i in owned])
    assert xi is not None
    assert len(xi["xi"]) == 11
    assert xi["captain"] in xi["xi"]


def test_suggests_the_upgrade():
    owned, by_id = _pool()
    sugg = suggest_transfers(owned, by_id, bank=0.0, free_transfers=1)
    assert sugg
    assert sugg[0]["in"]["id"] == 100    # brings in the star
    assert sugg[0]["gain"] > 0


def test_hit_cost_reduces_net_by_four():
    owned, by_id = _pool()
    free = suggest_transfers(owned, by_id, bank=0.0, free_transfers=1)[0]
    on_hit = suggest_transfers(owned, by_id, bank=0.0, free_transfers=0)[0]
    assert abs(on_hit["net"] - (free["net"] - 4.0)) < 1e-9
