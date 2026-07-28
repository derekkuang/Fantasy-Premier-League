"""Squad balance check: metrics and flags."""

from fpledge.balance import check_balance


def _squad():
    players, i = [], 0
    for pos, n in [("GK", 2), ("DEF", 5), ("MID", 5), ("FWD", 3)]:
        for k in range(n):
            players.append(
                {"name": f"{pos}{k}", "position": pos, "price": 5.0, "team": f"T{i % 6}",
                 "xp": 5.0 - (i % 5) * 0.5, "ownership": 20.0, "x_minutes": 85.0,
                 "starter": False, "captain": False}
            )
            i += 1

    def mark(pos, count):
        c = 0
        for p in players:
            if p["position"] == pos and not p["starter"] and c < count:
                p["starter"], c = True, c + 1

    mark("GK", 1); mark("DEF", 4); mark("MID", 4); mark("FWD", 2)  # a valid 4-4-2 XI
    max((p for p in players if p["starter"]), key=lambda p: p["xp"])["captain"] = True
    return players


def test_metrics_basic():
    r = check_balance(_squad(), budget=100.0)
    assert r["n_players"] == 15
    assert r["total_cost"] == 75.0 and r["budget_left"] == 25.0   # 15 x £5
    assert r["max_from_club"] <= 3
    assert r["flags"]


def test_concentration_flag():
    players = _squad()
    for i, p in enumerate(players):
        p["team"] = "A" if i < 8 else "B"       # force onto two clubs
    r = check_balance(players)
    assert any("concentration" in msg for _, msg in r["flags"])


def test_dead_bench_flag():
    players = _squad()
    bench = [p for p in players if not p["starter"]]
    bench[0]["x_minutes"] = bench[1]["x_minutes"] = 0.0
    r = check_balance(players)
    assert r["dead_bench"] >= 2
    assert any("bench" in msg.lower() for _, msg in r["flags"])
