"""Transfer suggester — the best single transfer by xP gain, net of the -4 hit.

For each ownable swap (same position, affordable from the bank, ≤3 per club after the move),
re-picks the best XI + captain and scores the total-xP gain. Beyond the free transfers, each
move costs 4 points, so the NET gain is what actually matters.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from .models.optimizer import MAX_PER_CLUB, best_xi

HIT_COST = 4.0


def suggest_transfers(
    current_ids: Sequence,
    pool_by_id: dict,
    bank: float = 0.0,
    free_transfers: int = 1,
    top: int = 5,
) -> list[dict]:
    """Rank single transfers by net xP gain.

    current_ids: the 15 owned player ids. pool_by_id: id -> player dict (id, name, position,
    price, team_id, team_name, xp). bank: spare £m. Returns the best `top` moves.
    """
    current_set = set(current_ids)
    base = best_xi([pool_by_id[i] for i in current_ids])
    if base is None:
        return []
    base_xp = base["total_xp"]
    club = Counter(pool_by_id[i]["team_id"] for i in current_ids)
    hit = 0.0 if free_transfers >= 1 else HIT_COST

    out = []
    for oid in current_ids:
        op = pool_by_id[oid]
        for ip in pool_by_id.values():
            if ip["id"] in current_set or ip["position"] != op["position"]:
                continue
            if ip["price"] - op["price"] > bank + 1e-9:                 # can't afford
                continue
            if ip["team_id"] != op["team_id"] and club[ip["team_id"]] >= MAX_PER_CLUB:
                continue                                                # would break 3-per-club
            new_ids = (current_set - {oid}) | {ip["id"]}
            new = best_xi([pool_by_id[i] for i in new_ids])
            if new is None:
                continue
            gain = new["total_xp"] - base_xp
            out.append({
                "out": op, "in": ip,
                "cost": round(ip["price"] - op["price"], 1),
                "gain": round(gain, 2),
                "net": round(gain - hit, 2),
            })
    out.sort(key=lambda r: r["net"], reverse=True)
    return out[:top]
