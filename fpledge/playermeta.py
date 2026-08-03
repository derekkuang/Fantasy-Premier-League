"""Per-player context from the FPL bootstrap blob: availability, form, price momentum,
set-piece duties.

None of this changes a projection — the minutes model already consumes availability, and the
rest is descriptive. What it changes is whether the numbers can be EXPLAINED. A record showing
0.00 xP is indistinguishable from a broken model until it can say "injured, out until 21 Aug",
and a quietly 25%-discounted projection looks like noise until it says "75% chance to play".

All of it comes from `bootstrap-static`, which is already landed by the ingest — so this is a
parse of data we hold, not a new data source. Keyed by FPL `code` (stable across seasons)
to match the rest of the pipeline.

PRESEASON REALITY (verify before reading signal into these): `form`, `cost_change_*` and
`transfers_*_event` are all zero until the season starts — they are wired now so they light up
on their own. `status`/`news` and the set-piece orders are live year-round.
"""

from __future__ import annotations

from .models.minutes import availability_factor

# What each FPL status code means, for the UI to render without re-deriving the vocabulary.
STATUS_LABEL = {
    "a": "available",
    "d": "doubtful",
    "i": "injured",
    "s": "suspended",
    "u": "unavailable",
    "n": "not in squad",
    "o": "out on loan",
}


def _f(v, default: float | None = 0.0) -> float | None:
    """FPL sends several numeric fields as strings (and sometimes null). Parse defensively."""
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def player_meta(boot: dict) -> dict[str, dict]:
    """{player_code: context} for every element in a bootstrap payload.

    `availability.factor` is the exact multiplier the minutes model applied, so the serving
    layer can attribute a discounted xP to availability rather than leaving it a mystery.
    """
    out: dict[str, dict] = {}
    for e in boot.get("elements", []):
        status = e.get("status")
        chance = e.get("chance_of_playing_next_round")
        t_in = int(e.get("transfers_in_event") or 0)
        t_out = int(e.get("transfers_out_event") or 0)
        out[e["code"]] = {
            "availability": {
                "status": status,
                "label": STATUS_LABEL.get(status, status),
                "chance": chance,
                "factor": availability_factor(chance, status),
                "news": (e.get("news") or "").strip(),
                "news_added": e.get("news_added"),
            },
            "recent": {
                # form = mean points over the last 30 days; ppg is season-to-date and survives
                # the preseason reset, so it is the honest fallback while form is still 0.
                "form": _f(e.get("form")),
                "points_per_game": _f(e.get("points_per_game")),
                "ep_next": _f(e.get("ep_next"), None),  # FPL's OWN projection — our benchmark
            },
            # NOT "price" — a record already has `price` (the player's cost in £m) and this
            # bundle is spread onto it, so that key would silently overwrite the cost with a
            # dict and break every budget calculation downstream.
            "price_moves": {
                # FPL prices are in tenths of a million; express deltas in £m like every
                # other price in this codebase.
                "change_event": round(int(e.get("cost_change_event") or 0) / 10.0, 1),
                "change_start": round(int(e.get("cost_change_start") or 0) / 10.0, 1),
                "transfers_in": t_in,
                "transfers_out": t_out,
                "net_transfers": t_in - t_out,
            },
            "set_pieces": {
                # 1 = first choice. None = no listed duty (the common case).
                "penalties": e.get("penalties_order"),
                "corners": e.get("corners_and_indirect_freekicks_order"),
                "freekicks": e.get("direct_freekicks_order"),
            },
        }
    return out


# The shape a record gets when a player is missing from the bootstrap (defensive: keeps the
# serving contract total, so the frontend never has to null-check a whole branch).
EMPTY_META = {
    "availability": {"status": None, "label": None, "chance": None, "factor": 1.0,
                     "news": "", "news_added": None},
    "recent": {"form": 0.0, "points_per_game": 0.0, "ep_next": None},
    "price_moves": {"change_event": 0.0, "change_start": 0.0, "transfers_in": 0,
                    "transfers_out": 0, "net_transfers": 0},
    "set_pieces": {"penalties": None, "corners": None, "freekicks": None},
}
