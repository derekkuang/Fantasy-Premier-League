"""Season simulation: FPL rule fidelity, and no leakage.

A season total is a number people will quote, so the rules underneath it have to be right. Most
of these tests are about the ways a simulator flatters itself: free profit on sales, bench points
that a real manager would never have collected, a captain who did not play still doubling.

The `actual`/`minutes` fields are the OUTCOME. They may only ever be read to score a decision
after it is made. A simulator that peeks would produce a spectacular season and mean nothing.
"""

from __future__ import annotations

import pytest

from fpledge.eval.season_sim import (
    MAX_FREE_TRANSFERS,
    auto_subs,
    score_gameweek,
    sell_price,
    simulate_season,
)


# --- selling price ------------------------------------------------------------------------ #
def test_you_keep_half_the_profit_rounded_down():
    """FPL's rule, and the one a lazy simulator gets wrong in its own favour: 50% of the rise,
    rounded DOWN to £0.1m. Prices here are tenths, so 55 -> 60 returns 57, not 60 and not 57.5."""
    assert sell_price(55, 60) == 57
    assert sell_price(55, 56) == 55        # a 0.1 rise is taxed away entirely
    assert sell_price(55, 57) == 56


def test_a_loss_is_refunded_in_full():
    """The tax is on profit only — selling at a loss returns the current price, not less."""
    assert sell_price(60, 55) == 55
    assert sell_price(60, 60) == 60


# --- auto-substitutions ------------------------------------------------------------------- #
def _p(pid, pos, xp=1.0, actual=0, minutes=0):
    return {"id": pid, "position": pos, "xp": xp, "actual": actual, "minutes": minutes}


def _legal_xi():
    return [
        _p(1, "GK", minutes=90), *[_p(i, "DEF", minutes=90) for i in (2, 3, 4, 5)],
        *[_p(i, "MID", minutes=90) for i in (6, 7, 8, 9)], *[_p(i, "FWD", minutes=90) for i in (10, 11)],
    ]


def test_a_starter_who_did_not_play_is_replaced_in_bench_order():
    xi = _legal_xi()
    xi[5] = _p(6, "MID", minutes=0)                       # a midfielder blanked
    bench = [_p(12, "MID", minutes=90), _p(13, "MID", minutes=90)]
    final, subs = auto_subs(xi, bench, {p["id"]: p["minutes"] for p in [*xi, *bench]})
    assert subs == [(6, 12)]                              # the FIRST bench player, not the best
    assert {p["id"] for p in final} == {1, 2, 3, 4, 5, 12, 7, 8, 9, 10, 11}


def test_a_bench_player_who_also_blanked_is_skipped():
    xi = _legal_xi()
    xi[5] = _p(6, "MID", minutes=0)
    bench = [_p(12, "MID", minutes=0), _p(13, "MID", minutes=90)]
    _final, subs = auto_subs(xi, bench, {p["id"]: p["minutes"] for p in [*xi, *bench]})
    assert subs == [(6, 13)]


def test_only_a_goalkeeper_can_replace_a_goalkeeper():
    """The rule that a naive 'first bench player who played' implementation breaks, producing a
    formation with no keeper and a season total that is quietly too high."""
    xi = _legal_xi()
    xi[0] = _p(1, "GK", minutes=0)
    bench = [_p(12, "MID", minutes=90), _p(13, "GK", minutes=90)]
    final, subs = auto_subs(xi, bench, {p["id"]: p["minutes"] for p in [*xi, *bench]})
    assert subs == [(1, 13)]
    assert sum(1 for p in final if p["position"] == "GK") == 1


def test_a_substitution_that_would_break_the_formation_is_refused():
    """Three defenders is the minimum. Losing one and having only a forward on the bench means
    the sub cannot happen — FPL leaves you with ten men, and so must this."""
    xi = [
        _p(1, "GK", minutes=90), *[_p(i, "DEF", minutes=90) for i in (2, 3)], _p(4, "DEF", minutes=0),
        *[_p(i, "MID", minutes=90) for i in (6, 7, 8, 9, 12)], *[_p(i, "FWD", minutes=90) for i in (10, 11)],
    ]
    bench = [_p(13, "FWD", minutes=90)]                   # would make it 2 DEF / 4 FWD
    _final, subs = auto_subs(xi, bench, {p["id"]: p["minutes"] for p in [*xi, *bench]})
    assert subs == []


def test_a_full_squad_of_players_who_all_played_makes_no_subs():
    xi = _legal_xi()
    bench = [_p(12, "MID", minutes=90)]
    _final, subs = auto_subs(xi, bench, {p["id"]: p["minutes"] for p in [*xi, *bench]})
    assert subs == []


# --- captaincy and scoring ---------------------------------------------------------------- #
def _pool(players):
    return {p["id"]: p for p in players}


def test_the_captain_is_doubled():
    xi = _legal_xi()
    xi[9] = _p(10, "FWD", actual=12, minutes=90)
    pool = _pool([*xi, _p(12, "MID", minutes=90)])
    res = score_gameweek([p["id"] for p in xi], 10, 11, [12], pool)
    assert res["raw_points"] == 12 + 12                   # everyone else scored 0


def test_the_armband_passes_to_the_vice_when_the_captain_does_not_play():
    xi = _legal_xi()
    xi[9] = _p(10, "FWD", actual=0, minutes=0)            # captain blanked
    xi[10] = _p(11, "FWD", actual=9, minutes=90)          # vice played
    pool = _pool([*xi, _p(12, "FWD", actual=2, minutes=90)])
    res = score_gameweek([p["id"] for p in xi], 10, 11, [12], pool)
    assert res["captain"] == 11
    assert res["captain_points"] == 9


def test_the_armband_stays_put_if_the_vice_also_blanked():
    xi = _legal_xi()
    xi[9] = _p(10, "FWD", actual=0, minutes=0)
    xi[10] = _p(11, "FWD", actual=0, minutes=0)
    pool = _pool([*xi, _p(12, "FWD", actual=3, minutes=90)])
    res = score_gameweek([p["id"] for p in xi], 10, 11, [12], pool)
    assert res["captain"] == 10


def test_hits_are_subtracted_from_the_total():
    xi = _legal_xi()
    xi[9] = _p(10, "FWD", actual=10, minutes=90)
    pool = _pool([*xi, _p(12, "MID", minutes=90)])
    clean = score_gameweek([p["id"] for p in xi], 10, 11, [12], pool, hits=0)
    hit = score_gameweek([p["id"] for p in xi], 10, 11, [12], pool, hits=2)
    assert hit["points"] == clean["points"] - 8
    assert hit["raw_points"] == clean["raw_points"]       # raw is before the hit


def test_bench_points_count_only_players_who_stayed_benched():
    """A benched player who is auto-subbed IN has scored for the XI; counting him as bench
    points too would double him."""
    xi = _legal_xi()
    xi[5] = _p(6, "MID", minutes=0)
    bench = [_p(12, "MID", actual=7, minutes=90), _p(13, "MID", actual=5, minutes=90)]
    pool = _pool([*xi, *bench])
    res = score_gameweek([p["id"] for p in xi], 1, 2, [12, 13], pool)
    assert res["bench_points"] == 5                       # 12 came on, 13 did not


# --- the loop, rules and leakage ---------------------------------------------------------- #
def _season_pool(n_gw=6, n_players=40):
    """A synthetic league big enough to field a legal squad under every constraint."""
    pool = {}
    for gw in range(1, n_gw + 1):
        entry = {}
        pid = 0
        for pos, count in (("GK", 6), ("DEF", 12), ("MID", 12), ("FWD", 10)):
            for k in range(count):
                pid += 1
                entry[pid] = {
                    "id": pid, "position": pos, "team_id": pid % 12, "price": 40.0 + (k % 5),
                    "xp": float(k), "fpl_xp": float(count - k), "ownership": float(k),
                    "actual": k, "minutes": 90,
                }
        pool[gw] = entry
    return pool


def test_the_simulator_runs_and_respects_the_budget():
    pool = _season_pool()
    r = simulate_season(pool, projection="xp", budget=1000.0)
    assert r["gameweeks"] == 6
    assert r["total_points"] > 0


def test_a_mistyped_projection_fails_loudly():
    """Silently defaulting to zero would simulate a season of arbitrary picks and report a
    number that looks like a result."""
    with pytest.raises(KeyError, match="no player carries the projection"):
        simulate_season(_season_pool(), projection="not_a_key")


def test_future_gameweeks_cannot_change_earlier_decisions():
    """The flagship check. Corrupting the LAST gameweek's realised points and projections must
    leave every earlier gameweek's score untouched."""
    clean = _season_pool()
    dirty = _season_pool()
    for p in dirty[6].values():
        p["actual"] = 99
        p["xp"] = 99.0
    a = simulate_season(clean, projection="xp")
    b = simulate_season(dirty, projection="xp")
    early_a = [h["points"] for h in a["history"] if h["gw"] < 6]
    early_b = [h["points"] for h in b["history"] if h["gw"] < 6]
    assert early_a == early_b


def test_realised_points_never_drive_decisions():
    """Rewriting only `actual` — leaving every projection identical — must not change a single
    pick, only the score. If it changes the picks, the policy is reading the answer."""
    base = _season_pool()
    peek = _season_pool()
    for gw in peek.values():
        for p in gw.values():
            p["actual"] = 100 - p["id"]          # a completely different outcome ordering
    a = simulate_season(base, projection="xp", allow_transfers=True)
    b = simulate_season(peek, projection="xp", allow_transfers=True)
    assert a["total_transfers"] == b["total_transfers"]
    assert [h.get("captain") for h in a["history"]] == [h.get("captain") for h in b["history"]]


def test_free_transfers_never_exceed_the_cap():
    pool = _season_pool(n_gw=8)
    r = simulate_season(pool, projection="xp", allow_transfers=False)
    assert r["total_transfers"] == 0
    assert MAX_FREE_TRANSFERS == 2


def test_a_blank_gameweek_scores_zero_rather_than_being_skipped():
    """A squad member with no fixture is a blank, not missing data. Dropping the gameweek
    entirely would delete it from the season total and quietly flatter every policy."""
    pool = _season_pool(n_gw=4)
    missing = set(list(pool[3])[:8])                      # eight players have no GW3 row
    pool[3] = {k: v for k, v in pool[3].items() if k not in missing}
    r = simulate_season(pool, projection="xp")
    assert r["gameweeks"] == 4                            # GW3 still scored
    assert r["blank_player_gameweeks"] > 0
