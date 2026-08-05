"""Understat ingest: shot-level data, and the identity join it depends on.

This is the Tier-2 enrichment — the one that can say something about *where* a team attacks,
which the FPL API cannot. Two very different pieces live here, and the risk is lopsided:

  * `UnderstatClient` / `fetch_*` talk to Understat's JSON endpoints directly. Network-bound,
    slow, and fragile to upstream layout changes, but a failure is loud and obvious.
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
# attacked, Y across it.
#
# ORIENTATION — VERIFIED 2026-08-05, and the original assumption was BACKWARDS. This constant
# was written as True ("Y=0 is the attacking side's left") with a comment saying it must be
# checked before anything was labelled "left" to a user. It never was. The check:
#
#   Understat's own roster `position` codes encode a side — AML/AMR, DL/DR, ML/MR, FWL/FWR.
#   Take every player whose codes are consistently one-sided across 60 matches and who took
#   8+ shots, then compare that side against their mean shot Y. Over 70 players:
#
#       left-coded  (n=37): mean Y 0.572     33/37 above 0.5
#       right-coded (n=33): mean Y 0.436     29/33 below 0.5
#
#   Low Y is the attacking team's RIGHT. Confirmed independently by named one-sided players
#   (Salah 0.403, Saka 0.376, Porro 0.392 right; Son 0.576, Díaz 0.575, Robinson 0.654 left).
#
# The test is deliberately self-contained — Understat's position codes against Understat's own
# coordinates — so it needs no outside knowledge of who plays where and can be re-run whenever
# the upstream convention is in doubt. This is exactly the silent flip the original comment
# feared: every team's attack mirrored, and every number still entirely plausible.
Y_ZERO_IS_LEFT = False
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


# --- network adapters ------------------------------------------------------------------ #
# STATUS 2026-08-05: WORKING, against Understat's own JSON endpoints rather than the page HTML.
#
# The previous note here said `getMatchData/{id}` "now 404s" and that Tier-2 was blocked on
# upstream. Half right, and the wrong half was the actionable one. What actually happened:
#
#   * The match page really did stop embedding `shotsData = JSON.parse(...)`. That blob is gone
#     and it is not coming back — every scraper written against it, soccerdata 1.9.1 included,
#     breaks. That part of the diagnosis was correct.
#   * `getMatchData/{id}` did NOT disappear. It is the endpoint the site's own `match.min.js`
#     calls, and it serves shots and rosters as JSON. It answers 404 to a plain GET and 200 to
#     the same GET carrying `X-Requested-With: XMLHttpRequest`. A 404 to an unadorned request
#     reads exactly like a removed endpoint, which is how it was misread.
#
# So the entire blocker was one request header. Two things follow, both worth having:
#
#   * No browser impersonation is needed. Verified 2026-08-05: this module's honest
#     `config.HTTP_USER_AGENT` gets 200s. There is no Cloudflare challenge and no TLS
#     fingerprint check on these endpoints, so the `tls_requests` native-library saga that
#     dominated the last attempt was never load-bearing — it was soccerdata's transport, not
#     Understat's requirement.
#   * soccerdata is no longer a dependency of this project. It was pulled in for this module
#     alone, and it is a heavy, fragile package whose Understat reader is broken against the
#     current site anyway.
#
# Coverage note: a season is 380 matches = 380 requests, throttled. Only `isResult` fixtures
# carry data; unplayed ones are skipped rather than fetched and discarded.
_BASE = "https://understat.com"

# The whole fix. Understat's routers answer these paths only for XHR-marked requests; without
# it every one of them 404s, which looks like the endpoint is gone rather than like a rejected
# request. If Tier-2 breaks again, re-check this before concluding anything about the site.
_XHR_HEADERS = {"X-Requested-With": "XMLHttpRequest"}

UNDERSTAT_MIN_INTERVAL_S = 1.0   # a season is 380 calls; be a good citizen


class UnderstatClient:
    """Understat's JSON endpoints. Polite, no retries — add backoff before scheduling this."""

    def __init__(self, session=None, min_interval: float | None = None):
        import requests

        from .. import config

        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": config.HTTP_USER_AGENT,
            **_XHR_HEADERS,
        })
        self._timeout = config.HTTP_TIMEOUT
        self._last_call = 0.0
        self._min_interval = (
            UNDERSTAT_MIN_INTERVAL_S if min_interval is None else min_interval
        )

    def _throttle(self) -> None:
        import time

        dt = time.monotonic() - self._last_call
        if dt < self._min_interval:
            time.sleep(self._min_interval - dt)
        self._last_call = time.monotonic()

    def _get(self, path: str) -> dict:
        resp = self.session.get(f"{_BASE}/{path}", timeout=self._timeout)
        resp.raise_for_status()
        return resp.json()

    def league_season(self, season: int | str, league: str = "EPL") -> dict:
        """One call for a whole season: `teams`, `players` and `dates` (the 380 fixtures).

        `season` is the starting year, as Understat labels it — 2024 is 2024-25.
        """
        return self._get(f"getLeagueData/{league}/{season}")

    def match(self, match_id: int | str) -> dict:
        """`shots` and `rosters`, each split into `h`/`a`."""
        self._throttle()
        return self._get(f"getMatchData/{match_id}")


def _flatten_shots(payload: dict, match_id: str) -> list[dict]:
    """`{"h": [...], "a": [...]}` -> one list, each shot tagged with the side that took it."""
    out: list[dict] = []
    for side in ("h", "a"):
        for shot in payload.get("shots", {}).get(side, []) or []:
            out.append({**shot, "side": side, "match_id": str(shot.get("match_id", match_id))})
    return out


def fetch_season_shots(
    season: int | str,
    league: str = "EPL",
    client: UnderstatClient | None = None,
    on_progress=None,
) -> list[dict]:
    """Every shot in a season, as plain dicts carrying Understat's own keys (X, Y, xG, ...).

    Raises rather than returning partial data — a half-fetched season skews every share
    computed from it, and a quietly short season is exactly the kind of degradation that
    stays plausible. Unplayed fixtures are skipped, not failed on.
    """
    client = client or UnderstatClient()
    fixtures = client.league_season(season, league).get("dates", [])
    played = [f for f in fixtures if f.get("isResult")]

    shots: list[dict] = []
    for i, fixture in enumerate(played, start=1):
        mid = str(fixture["id"])
        shots.extend(_flatten_shots(client.match(mid), mid))
        if on_progress:
            on_progress(i, len(played), mid)
    return shots


def fetch_league_players(
    season: int | str,
    league: str = "EPL",
    client: UnderstatClient | None = None,
) -> list[dict]:
    """Season player list, reshaped into what `build_fpl_id_map` expects.

    Understat's own keys (`id`, `player_name`, `team_title`) are renamed here rather than in
    the join, so the join keeps one input shape whatever the upstream calls its columns.
    """
    client = client or UnderstatClient()
    players = client.league_season(season, league).get("players", [])
    return [
        {
            "understat_id": str(p["id"]),
            "name": p.get("player_name", ""),
            "team": p.get("team_title", ""),
            **{k: v for k, v in p.items() if k not in ("id", "player_name", "team_title")},
        }
        for p in players
    ]


def fetch_fixtures(
    season: int | str,
    league: str = "EPL",
    client: UnderstatClient | None = None,
) -> list[dict]:
    """The season's fixtures, including team-level xG and Understat's own W/D/L forecast."""
    client = client or UnderstatClient()
    return client.league_season(season, league).get("dates", [])


def team_shots_against(shots: Sequence[dict], fixtures: Sequence[dict]) -> dict:
    """Shots faced per team, per match — the input the saves model does not currently have.

    `x_saves` is presently `opp_lambda * 3 * (x_minutes/90)`, i.e. a linear function of
    expected goals conceded. That sets clean-sheet points and save points almost exactly
    against each other: a keeper behind a good defence takes the clean sheet and few saves, one
    behind a bad defence takes neither but many saves, and the two terms cancel into a flat
    ranking. Save volume actually tracks SHOTS FACED, which is a different quantity and is not
    currently modelled anywhere. This is the raw material for fixing that.

    Returns {team_title: {"matches": n, "shots_against": n, "per_match": float}}.
    """
    home = {str(f["id"]): f["h"]["title"] for f in fixtures if f.get("isResult")}
    away = {str(f["id"]): f["a"]["title"] for f in fixtures if f.get("isResult")}

    faced: dict = {}
    seen: dict = {}
    for shot in shots:
        mid = str(shot.get("match_id", ""))
        if mid not in home:
            continue
        # a shot taken by the home side is one FACED by the away side
        defending = away[mid] if shot.get("side") == "h" else home[mid]
        faced[defending] = faced.get(defending, 0) + 1
        seen.setdefault(defending, set()).add(mid)

    return {
        team: {
            "matches": len(seen[team]),
            "shots_against": n,
            "per_match": round(n / len(seen[team]), 2) if seen[team] else 0.0,
        }
        for team, n in sorted(faced.items())
    }
