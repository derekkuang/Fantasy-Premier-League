"""Play a whole season on the model's advice, and count the points.

WHY THIS EXISTS. Every accuracy number this project has published is a RANKING metric — per-
gameweek Spearman over players. The product does not rank. It decides: which fifteen to buy,
who starts, who is captain, whether a transfer is worth −4. Those are different questions, and
the gap between them is not rhetorical:

  * a +0.01 Spearman improvement may change no decision at all, because the players it reorders
    were never candidates; and
  * a monotone recalibration CANNOT move Spearman by construction, yet moves every threshold
    that matters — whether a transfer clears the hit, how big a captaincy edge looks.

So a season simulation is not a nicer presentation of the same result. It is the first
measurement of the thing the product actually does.

HOW IT IS SCORED. Point-in-time throughout: the projection driving GW N's decisions comes from
`validate_xp`, which sees only gameweeks before N. Realised points and minutes are consumed
ONLY to score decisions after they are made, never to make them.

RULES IMPLEMENTED, because a season total is meaningless if the rules are wrong:
  * 15-man squad, 2/5/5/3, max 3 per club, £100.0m budget
  * legal XI formations (1 GK, 3-5 DEF, 2-5 MID, 1-3 FWD), captain doubled
  * vice-captaincy — if the captain does not play, the armband passes
  * auto-substitutions in bench order, keeping the formation legal, GK only for GK
  * one free transfer per gameweek, rolling over to a maximum of two, −4 per extra transfer
  * selling price: you keep half your profit, rounded DOWN to £0.1m

DELIBERATELY NOT MODELLED, and each one flatters or handicaps in a stated direction:
  * CHIPS (wildcard, bench boost, triple captain, free hit). A real manager has them; the
    simulation does not. This HANDICAPS the simulated manager against a real one.
  * price changes as a decision input. Prices come from the dataset, so they move, but the
    policy never buys a player because he is about to rise.
  * multi-gameweek planning. One transfer is judged on the coming gameweek alone, so the policy
    is myopic in a way a good human is not.

The comparison that carries the weight is therefore NOT "did we beat a real manager". It is the
same simulator run on different projections — ours, FPL's, random — where every simplification
above cancels, because all three are equally handicapped.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from ..models.optimizer import FORMATION, SQUAD_QUOTA, best_xi
from ..transfers import HIT_COST, suggest_transfers

SQUAD_SIZE = 15
MAX_FREE_TRANSFERS = 2      # 2024-25 rules; 2025-26 raised the cap to 5
START_BUDGET = 1000.0       # tenths of a million, matching vaastav's `value`


def sell_price(bought: float, current: float) -> float:
    """What FPL pays you for a player. You keep half the profit, rounded DOWN to £0.1m.

    Prices here are tenths of a million (vaastav's `value`), so "round down to 0.1m" is integer
    division by 2. A loss is refunded in full — the tax is on profit only.
    """
    if current <= bought:
        return current
    return bought + (current - bought) // 2


@dataclass
class Squad:
    ids: set = field(default_factory=set)
    bought_at: dict = field(default_factory=dict)   # element -> price paid
    bank: float = 0.0
    free_transfers: int = 1

    def value(self, prices: dict) -> float:
        return sum(sell_price(self.bought_at[i], prices[i]) for i in self.ids if i in prices)


def auto_subs(xi: Sequence[dict], bench: Sequence[dict], minutes: dict) -> tuple[list, list]:
    """Apply FPL's auto-substitutions. Returns (final_xi, subs_made).

    A starter with zero minutes is replaced by the first bench player, IN BENCH ORDER, who
    played and leaves the formation legal. The goalkeeper is a special case: only the bench
    keeper can replace him, and he can replace nobody else.

    This matters more than it looks. Bench points are a real share of a season, and a simulator
    that silently scores a blank for every non-playing starter would understate every policy it
    tests by the same amount — which sounds harmless until the policies differ in how often
    they field players who do not start.
    """
    final = list(xi)
    subs = []
    outfield_bench = [p for p in bench if p["position"] != "GK"]
    gk_bench = [p for p in bench if p["position"] == "GK"]

    for i, p in enumerate(final):
        if minutes.get(p["id"], 0) > 0:
            continue
        pool = gk_bench if p["position"] == "GK" else outfield_bench
        for cand in list(pool):
            if minutes.get(cand["id"], 0) <= 0:
                continue
            trial = [*final[:i], cand, *final[i + 1:]]
            if _formation_legal(trial):
                final[i] = cand
                pool.remove(cand)
                subs.append((p["id"], cand["id"]))
                break
    return final, subs


def _formation_legal(xi: Sequence[dict]) -> bool:
    if len(xi) != 11:
        return False
    counts = {pos: sum(1 for p in xi if p["position"] == pos) for pos in SQUAD_QUOTA}
    return all(lo <= counts[pos] <= hi for pos, (lo, hi) in FORMATION.items())


def score_gameweek(xi_ids, captain_id, vice_id, bench_ids, pool, hits=0):
    """Realised points for one gameweek, with auto-subs, captaincy and hits applied."""
    xi = [pool[i] for i in xi_ids]
    bench = [pool[i] for i in bench_ids if i in pool]
    minutes = {i: pool[i]["minutes"] for i in pool}

    final_xi, subs = auto_subs(xi, bench, minutes)
    # The armband passes only if the captain genuinely did not play — being subbed OUT by the
    # auto-sub logic is the same condition, so this is checked on minutes, not on membership.
    captain = captain_id
    if minutes.get(captain_id, 0) <= 0 and minutes.get(vice_id, 0) > 0:
        captain = vice_id

    total = sum(p["actual"] for p in final_xi)
    if any(p["id"] == captain for p in final_xi):
        total += pool[captain]["actual"]
    return {
        "points": total - hits * HIT_COST,
        "raw_points": total,
        "hits": hits,
        "subs": subs,
        "captain": captain,
        "captain_points": pool[captain]["actual"] if captain in pool else 0,
        "bench_points": sum(
            pool[i]["actual"] for i in bench_ids
            if i in pool and i not in {p["id"] for p in final_xi}
        ),
    }


def _pick(pool, key):
    """The projection driving decisions, as `best_xi`/`suggest_transfers` expect it.

    `.get(key, 0.0)` is for blank-gameweek placeholders, which carry no projection because the
    player has no fixture. The caller validates the key exists somewhere in the pool, so a
    mistyped projection name still fails loudly rather than silently scoring every player zero.
    """
    return {i: {**p, "xp": float(p.get(key, 0.0) or 0.0)} for i, p in pool.items()}


def _initial_squad(pool, key, budget=START_BUDGET):
    """Best legal 15 for the opening gameweek, by ILP over the projection."""
    from ..models.optimizer import optimize_squad

    players = [
        {**p, "xp": p[key], "price": p["price"]}
        for p in pool.values() if p.get("price")
    ]
    res = optimize_squad(players, budget=budget)
    ids = set(res["squad"])
    return Squad(
        ids=ids,
        bought_at={i: pool[i]["price"] for i in ids},
        bank=budget - sum(pool[i]["price"] for i in ids),
        free_transfers=1,
    )


def _apply_transfers(squad, pool, key, max_transfers=1):
    """Take the best single transfer if it clears its cost. Returns (squad, n_transfers).

    Deliberately myopic and deliberately greedy — one move, judged on the coming gameweek. A
    real manager plans over a horizon and banks transfers; modelling that would be a different
    project. What matters here is that EVERY policy under comparison is myopic in the same way,
    so the difference between them is attributable to the projection rather than to the planner.
    """
    priced = _pick(pool, key)
    owned = [i for i in squad.ids if i in priced]
    if len(owned) < SQUAD_SIZE:
        return squad, 0                       # a player left the dataset; skip trading this week

    # Selling raises the player's sell price, not his current price, so the affordable bank is
    # computed per candidate inside suggest_transfers via `price`. Substitute sell prices for the
    # players we own so the arithmetic is FPL's rather than a flattering approximation.
    for i in owned:
        priced[i] = {**priced[i], "price": sell_price(squad.bought_at[i], pool[i]["price"])}

    moves = suggest_transfers(owned, priced, bank=squad.bank,
                              free_transfers=squad.free_transfers, top=1)
    if not moves:
        return squad, 0
    best = moves[0]
    # `net` is already the gain net of any -4 hit, because suggest_transfers was told how many
    # free transfers we hold. Comparing `gain` here instead would take hits it cannot repay.
    if best["net"] <= 0:
        return squad, 0                       # not worth it, bank the transfer

    out_id, in_id = best["out"]["id"], best["in"]["id"]
    proceeds = sell_price(squad.bought_at[out_id], pool[out_id]["price"])
    cost = pool[in_id]["price"]
    new_ids = (squad.ids - {out_id}) | {in_id}
    bought = {k: v for k, v in squad.bought_at.items() if k != out_id}
    bought[in_id] = cost
    return Squad(ids=new_ids, bought_at=bought,
                 bank=squad.bank + proceeds - cost,
                 free_transfers=squad.free_transfers), 1


def simulate_season(
    gw_pool: dict,
    projection: str = "xp",
    start_gw: int | None = None,
    end_gw: int | None = None,
    budget: float = START_BUDGET,
    allow_transfers: bool = True,
) -> dict:
    """Manage a season on `projection`, and report what it actually scored.

    `gw_pool` is {gw: {element_id: {id, position, team_id, price, xp, fpl_xp, actual, minutes}}}.
    `projection` selects the key that DRIVES decisions; `actual` and `minutes` are only ever read
    to score them afterwards.
    """
    gws = sorted(gw_pool)
    start = start_gw or gws[0]
    end = end_gw or gws[-1]
    gws = [g for g in gws if start <= g <= end]
    if not gws:
        raise ValueError("no gameweeks in range")

    # Position and club for every player who ever appears. A squad member with no row in a given
    # gameweek has a BLANK — his club is not playing — and a blank is a normal part of an FPL
    # season, not missing data. The first version skipped those gameweeks entirely, which
    # silently deleted three of thirty from the season total.
    #
    # PRICE IS DELIBERATELY NOT TAKEN FROM HERE. Position and club are static attributes, but a
    # price is a value that moves, and a table built from the whole pool up front holds the price
    # from the LAST gameweek a player appears in — the future. Selling a blanked player at a
    # price he has not reached yet is a small leak, and small leaks in this project have a
    # history of surviving review. `last_price` below carries the most recent price actually
    # observed at the time.
    meta: dict = {}
    for pool_n in gw_pool.values():
        for el, p in pool_n.items():
            meta[el] = {"id": el, "position": p["position"], "team_id": p["team_id"]}
    last_price: dict = {}

    if not any(projection in p for pool_n in gw_pool.values() for p in pool_n.values()):
        raise KeyError(
            f"no player carries the projection {projection!r} — a typo here would otherwise "
            "score every player zero and simulate a season of arbitrary picks"
        )

    squad = _initial_squad(gw_pool[gws[0]], projection, budget=budget)
    history, total, total_hits, total_transfers = [], 0.0, 0, 0
    blanks = 0

    for n in gws:
        pool = gw_pool[n]
        # Record prices as they are observed, BEFORE any decision is taken this gameweek, so a
        # blanked player is valued at the last price actually seen rather than a future one.
        for el, p in pool.items():
            last_price[el] = p["price"]
        transfers = 0
        if allow_transfers and n != gws[0]:
            squad, transfers = _apply_transfers(squad, pool, projection)
        hits = max(0, transfers - squad.free_transfers)
        squad.free_transfers = min(MAX_FREE_TRANSFERS,
                                   squad.free_transfers - transfers + 1)
        squad.free_transfers = max(squad.free_transfers, 0)

        # Fill blanks with a zero-scoring placeholder rather than dropping the player. He is
        # still in the squad, still occupies a slot and a position, and still cannot be started
        # to any effect — which is exactly what a blank gameweek does to a real manager, and is
        # the reason auto-subs exist.
        pool = dict(pool)
        for i in squad.ids:
            if i not in pool and i in meta:
                pool[i] = {**meta[i], "price": last_price.get(i, squad.bought_at.get(i, 0.0)),
                           "xp": 0.0, "fpl_xp": 0.0, "actual": 0, "minutes": 0}
                blanks += 1
        owned = [i for i in squad.ids if i in pool]
        if len(owned) < SQUAD_SIZE:
            history.append({"gw": n, "points": 0.0, "note": f"incomplete squad ({len(owned)}/15)"})
            continue

        picked = _pick(pool, projection)
        xi = best_xi([picked[i] for i in owned])
        if xi is None:
            history.append({"gw": n, "points": 0.0, "note": "no legal XI"})
            continue
        xi_ids = xi["xi"]
        bench_ids = [i for i in owned if i not in set(xi_ids)]
        # Bench order: best projection first, which is what a manager sets. The bench keeper is
        # separate and never competes with outfielders for a slot.
        bench_ids.sort(key=lambda i: picked[i]["xp"], reverse=True)
        vice = max((i for i in xi_ids if i != xi["captain"]),
                   key=lambda i: picked[i]["xp"], default=xi["captain"])

        res = score_gameweek(xi_ids, xi["captain"], vice, bench_ids, pool, hits=hits)
        total += res["points"]
        total_hits += hits
        total_transfers += transfers
        history.append({
            "gw": n, "points": res["points"], "raw_points": res["raw_points"],
            "hits": hits, "transfers": transfers, "captain": res["captain"],
            "captain_points": res["captain_points"], "bench_points": res["bench_points"],
            "n_subs": len(res["subs"]), "squad_value": squad.value(
                {i: p["price"] for i, p in pool.items()}) + squad.bank,
        })

    scored = [h for h in history if "raw_points" in h]
    return {
        "projection": projection,
        "gameweeks": len(scored),
        "total_points": total,
        "points_per_gw": total / len(scored) if scored else 0.0,
        "total_hits": total_hits,
        "total_transfers": total_transfers,
        "bench_points": sum(h["bench_points"] for h in scored),
        "captain_points": sum(h["captain_points"] for h in scored),
        "blank_player_gameweeks": blanks,
        "history": history,
    }


def build_gw_pool(player_rows, records, teams_name_to_id):
    """Assemble {gw: {element: {...}}} from vaastav rows plus `validate_xp` records.

    The projections come from `records`, which is the walk-forward's own output and therefore
    already point-in-time — GW N's number was produced without seeing GW N. Prices, positions,
    clubs and realised points come from the raw rows.

    Only players the walk-forward actually scored are included. That is a real restriction and
    it cuts in a specific direction: a player with no history yet (a new signing in his first
    gameweek) cannot be bought, exactly as our live model could not recommend him.
    """
    by_key: dict = {}
    for r in records:
        gw, el, my_xp, fpl_xp, actual, pos, minutes = r
        by_key[(gw, el)] = {
            "id": el, "position": pos, "xp": my_xp, "fpl_xp": fpl_xp,
            "actual": actual, "minutes": minutes,
        }

    pool: dict = {}
    for row in player_rows:
        key = (row["gw"], row["element"])
        rec = by_key.get(key)
        if rec is None:
            continue
        tid = teams_name_to_id.get(row["team"])
        if tid is None or not row.get("value"):
            continue
        entry = pool.setdefault(row["gw"], {})
        # A double gameweek gives one element two rows; the record already summed them, so keep
        # the first and do not double-count price or club.
        entry.setdefault(row["element"], {
            **rec, "team_id": tid, "price": float(row["value"]),
            # Ownership, so "follow the crowd" can be run through the identical simulator as a
            # baseline. A template manager is the thing most FPL players actually are.
            "ownership": float(row.get("selected") or 0),
        })
    return pool
