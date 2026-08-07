"""Club news feeds — the raw material for team-news extraction.

WHY. §19 measured perfect team news at +0.168 played-only Spearman against +0.012 for the best
modelling change in the project, and §20 showed that knowing the starting eleven is 82% of that
prize. FPL's own `chance_of_playing_next_round` (captured free by `scripts/snapshot.py`) covers
the INJURY half. It says nothing about ROTATION — "we'll make changes with Thursday in mind" is
a starting-XI signal that never appears in an availability field, and rotation is exactly the
part of XI uncertainty injuries do not explain.

Press conferences are where both originate. This captures the feeds that report them.

RSS ONLY, AND DELIBERATELY SO. These are feeds a publisher emits for machine consumption, which
is a different posture from scraping article bodies. It also caps what is available: an RSS item
carries a headline and a one-line description, not the paragraph where the manager says who is
fit. That limit is real and is the reason this module captures rather than concludes — see the
extraction notes at the bottom.

WHY CAPTURE NOW. Feeds are a rolling window: BBC's per-club feeds carry roughly the last 4-24
items and older ones fall off permanently. Like the FPL snapshot and the props capture, history
cannot be bought back later at any price. Every day not captured is gone.

Verified live 2026-08-07: all 20 Premier League clubs return 200.
"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from html import unescape
from urllib.parse import urlparse

from .. import config

BBC_TEAM_FEED = "https://feeds.bbci.co.uk/sport/football/teams/{slug}/rss.xml"

# BBC's slug per club. Two do not follow the obvious pattern and 404 on the naive guess —
# checked individually rather than derived, because a silently 404ing club is a club whose team
# news simply never appears and nothing in the output would say so.
BBC_SLUGS = {
    "Arsenal": "arsenal",
    "Aston Villa": "aston-villa",
    "Bournemouth": "afc-bournemouth",                  # NOT "bournemouth"
    "Brentford": "brentford",
    "Brighton": "brighton-and-hove-albion",            # NOT "brighton"
    "Burnley": "burnley",
    "Chelsea": "chelsea",
    "Crystal Palace": "crystal-palace",
    "Everton": "everton",
    "Fulham": "fulham",
    "Leeds": "leeds-united",
    "Liverpool": "liverpool",
    "Man City": "manchester-city",
    "Man Utd": "manchester-united",
    "Newcastle": "newcastle-united",
    "Nott'm Forest": "nottingham-forest",
    "Sunderland": "sunderland",
    "Spurs": "tottenham-hotspur",
    "West Ham": "west-ham-united",
    "Wolves": "wolverhampton-wanderers",
}

MIN_INTERVAL_S = 1.0


class NewsFeedError(RuntimeError):
    pass


def _text(node, tag: str) -> str:
    el = node.find(tag)
    return unescape((el.text or "").strip()) if el is not None and el.text else ""


def parse_rss(xml_text: str) -> list[dict]:
    """RSS 2.0 items -> plain dicts. Raises on malformed XML rather than returning nothing.

    An empty list is a legitimate answer (a quiet club), so a parse failure must NOT produce one
    — the two would be indistinguishable in the index and a broken feed would read as a quiet
    week for the rest of the season.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise NewsFeedError(f"malformed RSS: {exc}") from exc
    out = []
    for item in root.iter("item"):
        out.append({
            "guid": _text(item, "guid") or _text(item, "link"),
            "title": _text(item, "title"),
            "summary": _text(item, "description"),
            "link": _text(item, "link"),
            "published": _text(item, "pubDate"),
        })
    return out


class NewsFeedClient:
    """Polite reader for publisher RSS. No article bodies are fetched."""

    def __init__(self, session=None, min_interval: float | None = None):
        import requests

        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": config.HTTP_USER_AGENT})
        self._timeout = config.HTTP_TIMEOUT
        self._min_interval = MIN_INTERVAL_S if min_interval is None else min_interval
        self._last = 0.0

    def _throttle(self) -> None:
        dt = time.monotonic() - self._last
        if dt < self._min_interval:
            time.sleep(self._min_interval - dt)
        self._last = time.monotonic()

    def club(self, club: str) -> list[dict]:
        """Recent items for one club, tagged with it."""
        slug = BBC_SLUGS.get(club)
        if slug is None:
            raise NewsFeedError(f"no feed slug for {club!r}")
        self._throttle()
        url = BBC_TEAM_FEED.format(slug=slug)
        resp = self.session.get(url, timeout=self._timeout)
        if resp.status_code != 200:
            raise NewsFeedError(f"{club}: HTTP {resp.status_code} from {urlparse(url).netloc}")
        return [{**it, "club": club, "source": "bbc"} for it in parse_rss(resp.text)]


# --- deterministic first pass ------------------------------------------------------------- #
# Everything below is pure, testable and needs no API key. It answers "which of our players is
# being talked about", which is already a signal — a manager discussing a player two days before
# a deadline is information, whatever he says — and it is the input an LLM pass would work from
# rather than being handed raw prose.
_WORD = re.compile(r"[^a-z ]+")

# Cheap intent cues. NOT a classifier and not treated as one: they route items for a closer look
# and are deliberately over-inclusive, because a missed rotation hint costs more than a
# false positive that a later stage discards.
CUES = {
    "injury": ("injur", "knock", "strain", "hamstring", "ankle", "groin", "calf", "out for",
               "sidelined", "ruled out", "surgery", "scan"),
    "return": ("return", "back in", "fit again", "available", "recovered", "in contention",
               "trained"),
    "rotation": ("rotat", "rest", "changes", "manage his", "minutes", "load", "freshen"),
    "suspension": ("suspend", "ban", "red card", "accumulat"),
}


def normalise(text: str) -> str:
    return _WORD.sub(" ", (text or "").lower()).strip()


def mentions(item: dict, players: list[dict]) -> list[dict]:
    """Which FPL players a feed item names.

    `players` are dicts with `element_id`, `web_name`, `full_name`, `team`. Matching is
    club-scoped — an item from the Arsenal feed can only mention Arsenal players — for the same
    reason `ingest.understat.build_fpl_id_map` never matches across teams: two players share a
    surname and only one is at the club.
    """
    hay = f" {normalise(item.get('title', ''))} {normalise(item.get('summary', ''))} "
    club = item.get("club")
    found = {}
    for p in players:
        if club and p.get("team") and p["team"] != club:
            continue
        for name in (p.get("web_name"), p.get("full_name")):
            if not name:
                continue
            n = normalise(name)
            # Whole-word only. Substring matching turns "Sels" into a hit on "vessels" and
            # every short surname into noise.
            if len(n) >= 4 and f" {n} " in hay:
                found[p["element_id"]] = {"element_id": p["element_id"], "name": name,
                                          "team": p.get("team")}
                break
    return list(found.values())


def cue_tags(item: dict) -> list[str]:
    """Which intent cues the text trips. Over-inclusive on purpose."""
    hay = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    return sorted(k for k, words in CUES.items() if any(w in hay for w in words))
