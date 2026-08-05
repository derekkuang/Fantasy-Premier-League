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

import html
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
    """Casefold, strip accents and punctuation: "Son Heung-min" -> "son heung min".

    HTML entities are decoded first. Understat serves names straight from its templates, so
    "Dara O'Shea" arrives as "Dara O&#039;Shea"; left encoded, the digits survive `NFKD` and
    are then stripped as punctuation, leaving "dara oshea" — which happens to be right, and
    "&amp;" would not be. Decoding is one call and removes the whole class.
    """
    if not name:
        return ""
    decomposed = unicodedata.normalize("NFKD", html.unescape(name))
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    lowered = ascii_only.lower().translate(_TRANSLITERATE).replace("-", " ").replace("'", "")
    return _SPACES.sub(" ", _PUNCT.sub(" ", lowered)).strip()


def surname(name: str) -> str:
    """The last token of a normalised name — how FPL's `web_name` usually renders a player."""
    parts = normalise_name(name).split()
    return parts[-1] if parts else ""


def _prefix_candidates(by_team_tokens: dict, team: str, name: str) -> list[dict]:
    """Players at `team` whose full name STARTS WITH every token of `name`, in order.

    This exists because FPL stores a player's full legal name while Understat uses the name
    he is known by, and under Spanish, Portuguese and Brazilian convention the extra tokens
    come LAST — the paternal surname is followed by the maternal one. So FPL has "David Raya
    Martin" and "Moisés Caicedo Corozo" where Understat has "David Raya" and "Moisés Caicedo",
    and `surname()` — which takes the last token — compares "martin" against "raya" and finds
    nothing. Before this rule the join silently dropped 93 of 562 players, among them full-
    season regulars (Raya, Caicedo, Cucurella, Dalot, Bruno Guimarães, Murillo), and the
    failure was concentrated by nationality: exactly the players whose names have that shape.

    It is not fuzzy matching, and it does not violate the join policy above. The comparison is
    exact on every token it uses, it stays scoped to one club, and a name that prefixes two
    players at the same club is reported ambiguous rather than guessed. It only ever ADDS
    tokens on the FPL side, never drops or transposes them: "Gabriel" prefixes both Arsenal
    Gabriels and is refused, as it should be.

    Two further shapes are accepted on the same terms, both observed in the same season:

      * the extra tokens are on the UNDERSTAT side ("Amad Diallo Traore" against FPL's "Amad
        Diallo"), which is the identical rule with the arguments swapped; and
      * the same tokens in a different ORDER ("Mitoma Kaoru" against "Kaoru Mitoma"), where
        the sources disagree about whether the family name comes first. Multiset equality is
        still exact on every token — nothing is dropped, added or approximated.

    What is deliberately NOT accepted is a name appearing in the MIDDLE of a longer one (FPL's
    "Francisco Evanilson de Lima Barbosa" for Understat's "Evanilson"). That is a substring
    test, it admits genuine coincidences, and the join's whole posture is that a missing player
    is a visible gap while a wrong one is an invisible lie.
    """
    want = normalise_name(name).split()
    if not want:
        return []
    out = []
    for p, tokens in by_team_tokens.get(team, ()):
        if len(tokens) > len(want) and tokens[: len(want)] == want:
            out.append(p)                                    # FPL name is longer
        elif len(want) > len(tokens) and want[: len(tokens)] == tokens:
            out.append(p)                                    # Understat name is longer
        elif len(want) == len(tokens) and sorted(want) == sorted(tokens) and want != tokens:
            out.append(p)                                    # same tokens, reordered
    return out


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
    by_team_tokens: dict[str, list[tuple[dict, list[str]]]] = defaultdict(list)
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
            by_team_tokens[team].append((p, alias.split()))

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

        by_prefix = _distinct(_prefix_candidates(by_team_tokens, team, name))
        if len(by_prefix) == 1:
            out[uid] = by_prefix[0]["element_id"]
            matched_by[uid] = "prefix"
            continue
        if len(by_prefix) > 1:
            ambiguous.append({**u, "reason": "several players at the club start with this name"})
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


# --- fitting the match engine on xG rather than goals ------------------------------------ #
# Goals are a noisy realisation of team strength; xG estimates the same thing with less
# variance. Measured on this project's walk-forward (docs/HANDOFF.md §19): fitting the engine on
# xG lifts played-only per-GW Spearman by +0.0088 pooled over 2023-24 and 2024-25, 95% CI
# [+0.0042, +0.0135], 38/60 gameweeks improved.
#
# TWO THINGS TO KNOW BEFORE USING IT.
#
# 1. It switches OFF the Dixon-Coles tau correction. Those masks test for exact integer
#    scorelines (0-0, 1-0, 0-1, 1-1) and continuous xG matches none of them, so what you are
#    fitting is Poisson-on-xG rather than Dixon-Coles-on-xG. Measured separately, tau is worth
#    -0.0002 to player ranking, so this costs nothing here — but it is not nothing for a model
#    predicting exact scorelines, which is what tau exists for.
# 2. A PARTIAL substitution is a different model on different seasons. Understat covers the
#    top five leagues from 2014-15; anything older, or any match that fails to join, keeps its
#    real goals. That is a defensible fallback and a terrible silent default, so the report is
#    returned rather than logged and the caller is expected to look at it.
_XG_NAME_OVERRIDES = {
    # Football-Data name -> Understat title, for the pairs fuzzy matching gets wrong.
    "Man United": "Manchester United",
    "Man City": "Manchester City",
    "Nott'm Forest": "Nottingham Forest",
    "Wolves": "Wolverhampton Wanderers",
    "Newcastle": "Newcastle United",
    "Sheffield United": "Sheffield United",
}


def build_xg_name_map(engine_names: Sequence[str], understat_titles: Sequence[str]) -> dict:
    """Map the engine's team names onto Understat titles, exactly or not at all."""
    from .idmap import name_similarity

    titles = set(understat_titles)
    out: dict = {}
    for name in engine_names:
        override = _XG_NAME_OVERRIDES.get(name)
        if override and override in titles:
            out[name] = override
            continue
        best, score = None, 0.0
        for t in understat_titles:
            s = name_similarity(name, t)
            if s > score:
                best, score = t, s
        out[name] = best if score >= 0.6 else None
    return out


def substitute_xg(
    matches: Sequence[dict],
    understat_fixtures: Sequence[dict],
    name_map: dict | None = None,
    max_day_gap: int = 1,
) -> tuple[list[dict], dict]:
    """Replace each match's goals with its Understat xG where the two can be joined.

    Joins on (home, away, date) with a day of slack, because Understat timestamps kickoffs in
    UTC while Football-Data records local dates and the two disagree either side of midnight.
    Never joins on teams alone: a season contains each pairing twice.

    Returns `(matches, report)`. **Read the report.** `substituted` below `total` means the fit
    is part xG and part goals, which is a different model on different seasons — supportable,
    but only if it is stated.
    """
    from datetime import UTC, datetime

    titles = sorted({f["h"]["title"] for f in understat_fixtures}
                    | {f["a"]["title"] for f in understat_fixtures})
    engine_names = sorted({m["home"] for m in matches} | {m["away"] for m in matches})
    name_map = name_map or build_xg_name_map(engine_names, titles)

    def _ord(s: str) -> int:
        return datetime.strptime(s[:10], "%Y-%m-%d").replace(tzinfo=UTC).date().toordinal()

    index: dict = {}
    for f in understat_fixtures:
        if not f.get("isResult"):
            continue
        key = (f["h"]["title"], f["a"]["title"])
        index.setdefault(key, []).append((_ord(f["datetime"]), f))

    out, substituted, unmatched = [], 0, []
    for m in matches:
        h, a = name_map.get(m["home"]), name_map.get(m["away"])
        hit = None
        if h and a:
            day = _ord(m["date"])
            for cand_day, f in index.get((h, a), []):
                if abs(cand_day - day) <= max_day_gap:
                    hit = f
                    break
        if hit is None:
            out.append(dict(m))
            unmatched.append((m.get("season"), m["home"], m["away"], m["date"]))
            continue
        out.append({**m, "home_goals": float(hit["xG"]["h"]), "away_goals": float(hit["xG"]["a"])})
        substituted += 1

    return out, {
        "total": len(matches),
        "substituted": substituted,
        "share": round(substituted / len(matches), 3) if matches else 0.0,
        "unmapped_teams": sorted(n for n, t in name_map.items() if t is None),
        "unmatched_sample": unmatched[:10],
        "n_unmatched": len(unmatched),
    }
