"""The advisor's tool surface: everything the model is allowed to ask for.

The model never computes. It chooses which of these to call and with what arguments; every
number in its answer came back from one of them, out of the same engine that powers the rest
of the site. That is a structural guarantee rather than a checked one — there is no path by
which it can invent an xP, because it has no way to produce one.

Two design rules run through this file:

1. TOKEN DISCIPLINE. Each return value is re-sent to the API on every subsequent turn of the
   conversation, so a fat payload is billed again and again. Every method returns the few
   fields a decision actually needs, and `search_players` is capped hard. This is the main
   cost lever in the whole feature.
2. TOOLS ENFORCE THE RULES. Legality (2/5/5/3, max 3 per club, the budget, the -4 hit) is
   checked here, not described in the prompt and hoped for. An illegal move comes back as a
   refusal with a reason the model can act on, so it self-corrects instead of recommending
   something the game would reject.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Any

from ..balance import check_balance
from ..models.optimizer import best_xi

SQUAD_QUOTA = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
MAX_PER_CLUB = 3
HIT_COST = 4.0
MAX_SEARCH_RESULTS = 12   # every extra row is re-billed on every later turn


def _pool_dict(r: dict) -> dict:
    """Serving record -> the id/name shape the optimizer and transfer code expect."""
    return {
        "id": r["element_id"], "name": r["web_name"], "position": r["position"],
        "price": r["price"], "team_id": r["team_id"], "team_name": r["team_name"],
        "xp": r["xp"], "ownership": r["ownership"], "x_minutes": r["x_minutes"],
    }


def _brief(p: dict, rec: dict | None = None) -> dict:
    """The compact player row the model sees. Deliberately small — see TOKEN DISCIPLINE."""
    out = {
        "id": p["id"], "name": p["name"], "pos": p["position"],
        "team": p["team_name"], "price": p["price"], "xp": round(p["xp"], 2),
        "owned_by": round(p.get("ownership", 0.0), 1),
    }
    if rec:
        avail = rec.get("availability") or {}
        if avail.get("status") and avail["status"] != "a":
            # only surfaced when it is actually news — an "available" flag on every row is
            # 20 wasted tokens per player per turn
            out["flag"] = avail.get("label")
            if avail.get("chance") is not None:
                out["chance_to_play"] = avail["chance"]
        if (rec.get("set_pieces") or {}).get("penalties") == 1:
            out["penalties"] = "first choice"
    return out


class AdvisorTools:
    """Bound to one manager's squad for the length of a conversation.

    Holding the squad here rather than passing an entry id into every call means the FPL API
    is touched once per conversation, not once per tool call.
    """

    def __init__(self, records: Sequence[dict], owned_ids: Sequence[int],
                 bank: float, free_transfers: int, ticker: dict | None = None):
        self.records = {r["element_id"]: r for r in records}
        # the transfer universe excludes promoted/low-data clubs, but the manager's own
        # players stay lookupable even if they fall in that bucket
        self.pool = {
            r["element_id"]: _pool_dict(r)
            for r in records if not r.get("low_cov") and r.get("price")
        }
        for eid in owned_ids:
            if eid in self.records:
                self.pool.setdefault(eid, _pool_dict(self.records[eid]))
        self.owned = [e for e in owned_ids if e in self.pool]
        self.bank = bank
        self.free_transfers = free_transfers
        self.ticker = ticker or {}

    # --- helpers ---------------------------------------------------------------------- #
    def _squad(self, ids: Sequence[int]) -> list[dict]:
        return [self.pool[i] for i in ids]

    def _legality(self, ids: Sequence[int]) -> list[str]:
        """Every FPL rule the proposed 15 breaks, in words the model can act on."""
        squad = self._squad(ids)
        problems = []
        counts = Counter(p["position"] for p in squad)
        for pos, need in SQUAD_QUOTA.items():
            if counts.get(pos, 0) != need:
                problems.append(f"squad must have exactly {need} {pos}, this has {counts.get(pos, 0)}")
        for team, n in Counter(p["team_name"] for p in squad).items():
            if n > MAX_PER_CLUB:
                problems.append(f"max {MAX_PER_CLUB} players per club, this has {n} from {team}")
        return problems

    # --- tools ------------------------------------------------------------------------ #
    def get_squad(self) -> dict:
        """The manager's current 15, their best XI, captain, bank and free transfers."""
        squad = self._squad(self.owned)
        xi = best_xi(squad)
        starters = set(xi["xi"]) if xi else set()
        return {
            "bank": round(self.bank, 1),
            "free_transfers": self.free_transfers,
            "squad_value": round(sum(p["price"] for p in squad), 1),
            "projected_points": round(xi["total_xp"], 2) if xi else None,
            "captain": next((p["name"] for p in squad if xi and p["id"] == xi["captain"]), None),
            "players": [
                {**_brief(p, self.records.get(p["id"])), "starting": p["id"] in starters}
                for p in sorted(squad, key=lambda p: (
                    ["GK", "DEF", "MID", "FWD"].index(p["position"]), -p["xp"]))
            ],
        }

    def search_players(
        self, position: str | None = None, max_price: float | None = None,
        min_price: float | None = None, team: str | None = None,
        max_ownership: float | None = None, exclude_owned: bool = True,
        limit: int = 8,
    ) -> dict:
        """Candidates matching the filters, best expected points first."""
        limit = max(1, min(int(limit), MAX_SEARCH_RESULTS))
        owned = set(self.owned)
        hits = [
            p for p in self.pool.values()
            if (position is None or p["position"] == position.upper())
            and (max_price is None or p["price"] <= max_price)
            and (min_price is None or p["price"] >= min_price)
            and (team is None or (p["team_name"] or "").lower() == team.lower())
            and (max_ownership is None or p["ownership"] <= max_ownership)
            and not (exclude_owned and p["id"] in owned)
        ]
        hits.sort(key=lambda p: p["xp"], reverse=True)
        return {
            "matches": len(hits),
            "showing": min(len(hits), limit),
            "players": [_brief(p, self.records.get(p["id"])) for p in hits[:limit]],
        }

    def simulate_transfers(self, moves: Sequence[dict]) -> dict:
        """Apply one or more out/in swaps and report the effect, or why the move is illegal.

        `moves` is [{"out_id": int, "in_id": int}, ...]. Handles multi-move plans, which is
        the case a single-transfer ranking cannot express — "sell X, and downgrade Y to
        afford him" is one decision, not two independent ones.
        """
        if not moves:
            return {"legal": False, "problems": ["no moves given"]}

        outs = [m.get("out_id") for m in moves]
        ins = [m.get("in_id") for m in moves]
        problems: list[str] = []
        for oid in outs:
            if oid not in self.owned:
                problems.append(f"player {oid} is not in the squad")
        for iid in ins:
            if iid not in self.pool:
                problems.append(f"player {iid} has no projection (promoted or low-data club)")
            elif iid in self.owned:
                problems.append(f"player {iid} is already owned")
        if problems:
            return {"legal": False, "problems": problems}

        spend = sum(self.pool[i]["price"] for i in ins) - sum(self.pool[o]["price"] for o in outs)
        new_bank = round(self.bank - spend, 1)
        new_ids = [i for i in self.owned if i not in set(outs)] + list(ins)

        problems = self._legality(new_ids)
        if new_bank < 0:
            problems.append(f"costs £{spend:.1f}m but only £{self.bank:.1f}m is in the bank")
        if problems:
            return {"legal": False, "problems": problems, "cost": round(spend, 1)}

        before = best_xi(self._squad(self.owned))
        after = best_xi(self._squad(new_ids))
        if after is None:
            return {"legal": False, "problems": ["the resulting squad cannot field a legal XI"]}

        hits = max(0, len(moves) - self.free_transfers)
        penalty = hits * HIT_COST
        gain = after["total_xp"] - (before["total_xp"] if before else 0.0)
        return {
            "legal": True,
            "cost": round(spend, 1),
            "bank_after": new_bank,
            "hits_taken": hits,
            "points_penalty": penalty,
            "projected_points_before": round(before["total_xp"], 2) if before else None,
            "projected_points_after": round(after["total_xp"], 2),
            "gain_before_hit": round(gain, 2),
            "net_gain": round(gain - penalty, 2),
            "new_captain": next(
                (self.pool[i]["name"] for i in new_ids if i == after["captain"]), None),
        }

    def fixture_run(self, team: str, horizon: int = 5) -> dict:
        """A club's upcoming fixtures with true difficulty (1 easiest .. 5 hardest)."""
        tid = next(
            (p["team_id"] for p in self.pool.values()
             if (p["team_name"] or "").lower() == team.lower()), None)
        if tid is None:
            return {"error": f"no club named {team!r}"}
        rows = self.ticker.get(str(tid)) or self.ticker.get(tid) or []
        return {
            "team": team,
            "fixtures": [
                {"gw": f["gw"], "opponent": f["opp"], "home": f["home"],
                 "attack_difficulty": f["attack_fdr"], "clean_sheet_difficulty": f["defence_fdr"]}
                for f in rows[:horizon]
            ],
        }

    def squad_health(self) -> dict:
        """Structural warnings about the squad: bench spend, club concentration, rotation."""
        squad = self._squad(self.owned)
        xi = best_xi(squad)
        starters = set(xi["xi"]) if xi else set()
        captain = xi["captain"] if xi else None
        rows = [
            {"name": p["name"], "position": p["position"], "price": p["price"],
             "team": p["team_name"], "xp": p["xp"], "ownership": p["ownership"],
             "x_minutes": p["x_minutes"], "starter": p["id"] in starters,
             "captain": p["id"] == captain}
            for p in squad
        ]
        bal = check_balance(rows)
        return {"flags": [{"level": lvl, "message": msg} for lvl, msg in bal["flags"]],
                "bench_spend": bal["bench_spend"],
                "captain_dependence": bal["captain_dependence"]}


# --- schemas the model sees ------------------------------------------------------------ #
# Descriptions are prescriptive about WHEN to call, not just what the tool does — recent
# models weight trigger conditions in the description heavily when deciding to reach for a
# tool. `strict` + `additionalProperties: false` means arguments validate exactly.
def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "name": name,
        "description": description,
        "strict": True,
        "input_schema": {
            "type": "object", "properties": properties,
            "required": required, "additionalProperties": False,
        },
    }


TOOL_SCHEMAS: list[dict[str, Any]] = [
    _tool(
        "get_squad",
        "Get the manager's current 15 players, their best XI, captain, bank and free "
        "transfers. Call this FIRST in any conversation about their team, before suggesting "
        "anything — you cannot advise on a squad you have not read.",
        {}, [],
    ),
    _tool(
        "search_players",
        "Find transfer candidates matching filters, ranked by expected points. Call this "
        "whenever you need to name a player to bring in; never suggest a player from memory, "
        "because prices, form and availability change every week.",
        {
            "position": {"type": "string", "enum": ["GK", "DEF", "MID", "FWD"],
                         "description": "Restrict to one position."},
            "max_price": {"type": "number", "description": "Most the player may cost, in £m."},
            "min_price": {"type": "number", "description": "Least the player may cost, in £m."},
            "team": {"type": "string", "description": "Restrict to one club by name."},
            "max_ownership": {"type": "number",
                              "description": "Ownership ceiling in percent, for differentials."},
            "exclude_owned": {"type": "boolean",
                              "description": "Leave out players already in the squad. Default true."},
            "limit": {"type": "integer", "description": f"How many to return, max {MAX_SEARCH_RESULTS}."},
        },
        [],
    ),
    _tool(
        "simulate_transfers",
        "Apply one or more out/in swaps and get the exact effect: cost, bank left, points "
        "hit, and projected points before and after. Call this before recommending ANY "
        "transfer — it is the only way to know whether a move is legal and whether it "
        "actually gains points. Pass several moves together to evaluate a plan such as "
        "funding an upgrade by downgrading elsewhere.",
        {
            "moves": {
                "type": "array",
                "description": "The swaps to apply together.",
                "items": {
                    "type": "object",
                    "properties": {
                        "out_id": {"type": "integer", "description": "Player id to sell."},
                        "in_id": {"type": "integer", "description": "Player id to buy."},
                    },
                    "required": ["out_id", "in_id"],
                    "additionalProperties": False,
                },
            },
        },
        ["moves"],
    ),
    _tool(
        "fixture_run",
        "Get a club's upcoming fixtures with difficulty ratings. Call this when the reason "
        "for a move is the schedule, or when the manager asks about a run of games.",
        {
            "team": {"type": "string", "description": "Club name."},
            "horizon": {"type": "integer", "description": "How many gameweeks ahead. Default 5."},
        },
        ["team"],
    ),
    _tool(
        "squad_health",
        "Get structural warnings about the squad: money on the bench, too many players from "
        "one club, rotation risk, captain dependence. Call this when asked for a general "
        "review, or when no single transfer looks worthwhile and the real problem may be "
        "the shape of the squad.",
        {}, [],
    ),
]
