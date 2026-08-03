"""Understat ingest: shot-level data, and the identity join it depends on.

This is the Tier-2 enrichment — the one that can say something about *where* a team attacks,
which the FPL API cannot. Two very different pieces live here, and the risk is lopsided:

  * `fetch_*` are thin adapters over `soccerdata`. Network-bound, slow, and fragile to
    upstream layout changes, but a failure is loud and obvious.
  * `build_fpl_id_map` joins Understat's player identities to FPL `element_id`. A failure
    here is SILENT: a mis-joined player quietly attributes one man's shots to another, and
    every downstream number stays plausible. This is the highest-risk piece in the project,
    so it is deliberately conservative.

Join policy (why it refuses more than it could):
  * Never match across teams. Two players can share a surname; only one plays for the club.
  * Exact normalised name wins. Then a unique surname within the club. Nothing else.
  * No global fuzzy matching, no edit-distance thresholds, no "best guess". An ambiguous name
    is reported unmatched rather than guessed — a missing player is a visible gap, a wrong
    player is an invisible lie.
  * `overrides` exists for the handful a human has checked by hand.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Sequence

# --- identity ------------------------------------------------------------------------- #
_PUNCT = re.compile(r"[^a-z ]+")
_SPACES = re.compile(r"\s+")

# Latin letters NFKD does NOT decompose — they are distinct letters, not base+diacritic, so
# they survive normalisation and are then stripped as punctuation. Left unhandled, "Ødegaard"
# normalises to "degaard" and never joins to anything. Every one of these appears in the
# Premier League.
_TRANSLITERATE = str.maketrans({
    "ø": "o", "æ": "ae", "œ": "oe", "å": "a", "ð": "d", "þ": "th",
    "ł": "l", "đ": "d", "ħ": "h", "ı": "i", "ß": "ss",
})


def normalise_name(name: str) -> str:
    """Casefold, strip accents and punctuation: "Son Heung-min" -> "son heung min"."""
    if not name:
        return ""
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    lowered = ascii_only.lower().translate(_TRANSLITERATE).replace("-", " ").replace("'", "")
    return _SPACES.sub(" ", _PUNCT.sub(" ", lowered)).strip()


def surname(name: str) -> str:
    """The last token of a normalised name — how FPL's `web_name` usually renders a player."""
    parts = normalise_name(name).split()
    return parts[-1] if parts else ""


def _distinct(candidates: Sequence[dict]) -> list[dict]:
    """One entry per player. A player is indexed under several aliases, so the same person can
    land in a bucket twice ("Bukayo Saka" and "Saka" share the surname key) — counting those
    as two people would report a clean match as ambiguous."""
    seen: dict = {}
    for p in candidates:
        seen.setdefault(p["element_id"], p)
    return list(seen.values())


def build_fpl_id_map(
    fpl_players: Sequence[dict],
    understat_players: Sequence[dict],
    overrides: dict | None = None,
) -> dict:
    """Map Understat player ids -> FPL element_ids.

    FPL entries carry `element_id`, `full_name` (or `web_name`) and `team`; Understat entries
    carry `understat_id`, `name` and `team`.

    Returns {"map", "matched_by", "unmatched", "ambiguous"}. The report matters as much as the
    map — coverage is the thing that quietly degrades after an upstream rename.
    """
    overrides = overrides or {}

    by_team_full: dict[tuple[str, str], list[dict]] = defaultdict(list)
    by_team_surname: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for p in fpl_players:
        team = normalise_name(p.get("team") or "")
        # Index EVERY name FPL knows the player by. Single-name Brazilians are the reason:
        # Understat calls him "Gabriel", FPL's full_name is "Gabriel Magalhaes", and only the
        # web_name matches. Indexing both aliases keeps the join team-scoped and still lets
        # ambiguity detection fire if two players at one club share an alias.
        aliases = {
            normalise_name(p.get("full_name") or ""),
            normalise_name(p.get("web_name") or ""),
        } - {""}
        for alias in aliases:
            by_team_full[(team, alias)].append(p)
            by_team_surname[(team, surname(alias))].append(p)

    out: dict = {}
    matched_by: dict = {}
    unmatched: list[dict] = []
    ambiguous: list[dict] = []

    for u in understat_players:
        uid = u["understat_id"]
        if uid in overrides:
            out[uid] = overrides[uid]
            matched_by[uid] = "override"
            continue

        team = normalise_name(u.get("team") or "")
        name = normalise_name(u.get("name") or "")

        exact = _distinct(by_team_full.get((team, name), []))
        if len(exact) == 1:
            out[uid] = exact[0]["element_id"]
            matched_by[uid] = "exact"
            continue
        if len(exact) > 1:
            ambiguous.append({**u, "reason": "several players share this name at the club"})
            continue

        by_last = _distinct(by_team_surname.get((team, surname(name)), []))
        if len(by_last) == 1:
            out[uid] = by_last[0]["element_id"]
            matched_by[uid] = "surname"
            continue
        if len(by_last) > 1:
            ambiguous.append({**u, "reason": "several players share this surname at the club"})
            continue

        unmatched.append(u)

    return {"map": out, "matched_by": matched_by, "unmatched": unmatched, "ambiguous": ambiguous}


def coverage(report: dict, understat_players: Sequence[dict]) -> float:
    """Share of Understat players joined to an FPL id — the health metric to alarm on."""
    total = len(understat_players)
    return round(len(report["map"]) / total, 3) if total else 0.0


# --- shot zones ----------------------------------------------------------------------- #
# Understat gives each shot an (X, Y) in [0, 1]: X along the pitch toward the goal being
# attacked, Y across it. ORIENTATION IS AN ASSUMPTION — we take Y=0 as the attacking side's
# LEFT. It is one constant to flip, and it MUST be verified against a club with a known strong
# flank before any of this is labelled "left" in user-facing copy: a silent flip would mirror
# every team's attack and still read entirely plausibly.
Y_ZERO_IS_LEFT = True
FLANK_EDGE = 1.0 / 3.0   # y below 1/3 and above 2/3 are the channels; the rest is central


def shot_zone(y: float) -> str:
    """Which channel a shot came from, from the attacking team's point of view."""
    if y < FLANK_EDGE:
        return "left" if Y_ZERO_IS_LEFT else "right"
    if y > 1.0 - FLANK_EDGE:
        return "right" if Y_ZERO_IS_LEFT else "left"
    return "central"


def zone_shares(shots: Sequence[dict]) -> dict:
    """Share of a team's shots originating in each channel, plus the counts behind them.

    This is the honest version of "they attack X% down the left": it is a share of SHOTS, not
    of possession, touches or attacks, and must be labelled that way wherever it appears.
    Opta-style attacking-side percentages are a different measurement that we do not have.
    """
    counts = {"left": 0, "central": 0, "right": 0}
    for s in shots:
        y = s.get("Y", s.get("y"))
        if y is None:
            continue
        counts[shot_zone(float(y))] += 1
    total = sum(counts.values())
    return {
        "shots": total,
        "counts": counts,
        "shares": (
            {k: round(v / total, 3) for k, v in counts.items()} if total
            else dict.fromkeys(counts, 0.0)
        ),
        # below this a share is noise, not a tendency — say so rather than printing a number
        "reliable": total >= MIN_SHOTS_FOR_SHARE,
    }


MIN_SHOTS_FOR_SHARE = 30


# --- soccerdata adapters (network) ----------------------------------------------------- #
# STATUS 2026-08-02: these two adapters DO NOT CURRENTLY WORK. Two separate problems, found by
# running them:
#
# 1. (fixed, but it will recur) soccerdata reaches Understat through `tls_requests`, which
#    dlopens a native `tls-client` library it downloads from a GitHub release on first use —
#    it needs a spoofed TLS fingerprint to get past Cloudflare. Its downloader uses
#    `urllib.urlopen(..., timeout=15)`, and the asset is 10.3 MB, so on a slow link the file
#    lands TRUNCATED. The symptom is misleading: not a network error but
#        OSError: Failed to download the required TLS library
#    and, if you place a partial file yourself, dlopen rejects it with "__TEXT load command
#    content extends beyond end of file". Fix: fetch the full asset with curl (verify the byte
#    count against the GitHub API's `size`) into tls_requests/bin/. In a container, bake it in.
#
# 2. (open, upstream) With the library loaded, the shot reader still fails: it requests
#    `understat.com/getMatchData/{id}`, which now 404s, and the match pages no longer embed the
#    `shotsData = JSON.parse(...)` blob everyone scraped. Understat restructured; soccerdata
#    1.9.1 has not caught up. So Tier-2 shot zones need either a newer soccerdata or a
#    hand-written scraper against whatever endpoint the site uses now.
#
# Everything above this line is pure and tested and does not depend on either.
def _understat(seasons):
    import soccerdata as sd

    return sd.Understat(leagues="ENG-Premier League", seasons=seasons)


def fetch_shots(seasons) -> list[dict]:
    """Every shot event for the given seasons, as plain dicts.

    Network-bound and slow (Understat is scraped; soccerdata caches to disk). Raises rather
    than returning partial data — a half-fetched season skews every share computed from it.
    """
    df = _understat(seasons).read_shot_events()
    return df.reset_index().to_dict("records")


def fetch_team_match_xg(seasons) -> list[dict]:
    """Per-match team xG for/against — the input an xG-based engine fit would use."""
    df = _understat(seasons).read_team_match_stats()
    return df.reset_index().to_dict("records")
