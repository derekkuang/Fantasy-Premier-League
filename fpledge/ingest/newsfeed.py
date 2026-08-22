"""Club news feeds — the raw material for team-news extraction.

WHY. §19 measured perfect team news at +0.168 played-only Spearman against +0.012 for the best
modelling change in the project, and §20 showed that knowing the starting eleven is 82% of that
prize. FPL's own `chance_of_playing_next_round` (captured free by `scripts/snapshot.py`) covers
the INJURY half. It says nothing about ROTATION — "we'll make changes with Thursday in mind" is
a starting-XI signal that never appears in an availability field, and rotation is exactly the
part of XI uncertainty injuries do not explain.

Press conferences are where both originate. This captures the feeds that report them.

PUBLISHER-EMITTED MACHINE INTERFACES ONLY, NEVER ARTICLE BODIES. That is the line, and it always
was — "RSS only" was a proxy for it that stopped being accurate once the Premier League's own
content API turned out to be the only route to eleven clubs' own words (§31). The test applied to
a source is: does the publisher serve this for machines, without authentication, without
pretending to be a browser? RSS passes. The PL content API passes — an honest User-Agent returns
200, exactly as with the Understat fix in §18. Fetching the HTML article a link points at does
not pass, and that has not changed.

Within that posture the useful lever is
MORE SOURCES rather than deeper ones, because how much text a feed carries is the publisher's
choice and it varies enormously:

    measured live 2026-08-11, per source: clubs covered, mean text, % naming an FPL player
        BBC per-club RSS         20/20    147 chars   22.0%
        Guardian per-club RSS    19/20    805 chars   40.8%
        club's own RSS            9/20  1,622 chars   33.9%
        PL content API           20/20    437 chars   38.6%

BBC gives a headline and a clause. The others give paragraphs — the difference between text a
keyword can route and text a model can read, which is why they were added. None of it is the
presser transcript; the ceiling is higher, not gone.

WHY CAPTURE NOW. Feeds are a rolling window: these carry roughly the last 4-24 items and older
ones fall off permanently. Like the FPL snapshot and the props capture, history cannot be bought
back later at any price. Every day not captured is gone.

Verified live 2026-08-11: all 20 clubs in the league return 200 on BBC; 19 of 20 on the Guardian
(no Brighton tag exists). Sources are ADDITIVE PER CLUB — a club missing from one is not an
error, a club missing from all of them is.
"""

from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from dataclasses import dataclass
from html import unescape
from urllib.parse import quote, urlparse

from .. import config
from .httpget import get_with_retries

BBC_TEAM_FEED = "https://feeds.bbci.co.uk/sport/football/teams/{slug}/rss.xml"
GUARDIAN_TEAM_FEED = "https://www.theguardian.com/football/{slug}/rss"

# BBC's slug per club. This is a LOOKUP, not the league — see `clubs_in_play` below.
#
# THE BUG THIS SHAPE EXISTS TO PREVENT. The first version hardcoded twenty clubs and called that
# the Premier League. Three of them (Burnley, West Ham, Wolves) had been relegated and three that
# had come up (Coventry, Hull, Ipswich) were absent, so three clubs contributed NO team news all
# season while three dead feeds were polled — and the run cheerfully reported "20/20 clubs",
# because it was counting its own wrong list rather than the league.
#
# League composition changes every single year. It is never a constant, and the FPL bootstrap
# already publishes the current twenty, so that is the authority. Keeping relegated clubs in this
# table costs nothing and means a promotion needs no code change.
BBC_SLUGS = {
    "Arsenal": "arsenal",
    "Aston Villa": "aston-villa",
    "Bournemouth": "afc-bournemouth",                  # NOT "bournemouth"
    "Brentford": "brentford",
    "Brighton": "brighton-and-hove-albion",            # NOT "brighton"
    "Burnley": "burnley",
    "Chelsea": "chelsea",
    "Coventry City": "coventry-city",
    "Crystal Palace": "crystal-palace",
    "Everton": "everton",
    "Fulham": "fulham",
    "Hull City": "hull-city",
    "Ipswich": "ipswich-town",
    "Ipswich Town": "ipswich-town",                    # FPL has used both short and full forms
    "Leeds": "leeds-united",
    "Leicester": "leicester-city",
    "Liverpool": "liverpool",
    "Luton": "luton-town",
    "Man City": "manchester-city",
    "Man Utd": "manchester-united",
    "Newcastle": "newcastle-united",
    "Nott'm Forest": "nottingham-forest",
    "Sheffield Utd": "sheffield-united",
    "Southampton": "southampton",
    "Sunderland": "sunderland",
    "Spurs": "tottenham-hotspur",
    "West Ham": "west-ham-united",
    "Wolves": "wolverhampton-wanderers",
}


# The Guardian's per-club tag feeds. Slug, then the channel title the feed must announce.
#
# THE QUIET FAILURE THIS GUARD EXISTS TO PREVENT. An unrecognised Guardian slug does not always
# 404 — `/football/albion/rss` returns HTTP 200 with twenty perfectly well-formed items, and they
# are the site-wide football feed. A typo would therefore pour league-wide news into one club's
# bucket and look healthier than a club with nothing, because it produces MORE items, not fewer.
# Status codes cannot catch that; only the channel title can, so every Guardian feed carries the
# title it is required to announce and a mismatch is an error.
#
# Guardian tag naming is inconsistent (`manchestercity` but `manchester-united`), so none of these
# are guessable — each was probed. See scripts/probe_news_feeds.py.
GUARDIAN_FEEDS = {
    "Arsenal": ("arsenal", "Arsenal | The Guardian"),
    "Aston Villa": ("aston-villa", "Aston Villa | The Guardian"),
    "Bournemouth": ("bournemouth", "Bournemouth | The Guardian"),
    "Brentford": ("brentford", "Brentford | The Guardian"),
    "Burnley": ("burnley", "Burnley | The Guardian"),
    "Chelsea": ("chelsea", "Chelsea | The Guardian"),
    "Coventry City": ("coventry", "Coventry City | The Guardian"),
    "Crystal Palace": ("crystalpalace", "Crystal Palace | The Guardian"),
    "Everton": ("everton", "Everton | The Guardian"),
    "Fulham": ("fulham", "Fulham | The Guardian"),
    "Hull City": ("hullcity", "Hull City | The Guardian"),
    "Ipswich": ("ipswichtown", "Ipswich Town | The Guardian"),
    "Ipswich Town": ("ipswichtown", "Ipswich Town | The Guardian"),
    "Leeds": ("leedsunited", "Leeds United | The Guardian"),
    "Leicester": ("leicestercity", "Leicester City | The Guardian"),
    "Liverpool": ("liverpool", "Liverpool | The Guardian"),
    "Luton": ("lutontown", "Luton Town | The Guardian"),
    "Man City": ("manchestercity", "Manchester City | The Guardian"),
    "Man Utd": ("manchester-united", "Manchester United | The Guardian"),
    "Newcastle": ("newcastleunited", "Newcastle United | The Guardian"),
    "Nott'm Forest": ("nottinghamforest", "Nottingham Forest | The Guardian"),
    "Sheffield Utd": ("sheffieldunited", "Sheffield United | The Guardian"),
    "Southampton": ("southampton", "Southampton | The Guardian"),
    "Spurs": ("tottenham-hotspur", "Tottenham Hotspur | The Guardian"),
    "Sunderland": ("sunderland", "Sunderland | The Guardian"),
    "West Ham": ("westhamunited", "West Ham United | The Guardian"),
    "Wolves": ("wolves", "Wolverhampton Wanderers | The Guardian"),
    # No Brighton tag exists on the Guardian. Their own site covers it — see OFFICIAL_FEEDS.
}

# The clubs' own sites. The richest feeds by a distance (1300-2700 chars of description against
# the Guardian's ~750 and BBC's ~90) and the closest thing to a primary source: this is where a
# club publishes its own press-conference write-up.
#
# Only nine clubs still emit one. The rest were probed at the usual paths AND checked for a
# declared <link rel="alternate" type="application/rss+xml"> on their homepage; they publish no
# feed at all, which is a boundary, not an oversight. Fetching their article bodies instead would
# cross the line this module draws deliberately, so those clubs simply have fewer sources.
#
# Signal density runs the other way to volume: a club's own feed carries ticket sales, kit
# launches and academy fixtures alongside the team news. That is downstream's problem — the
# mention/cue pass and the extraction step filter it — and more text with more noise still beats
# a headline, because a headline cannot be filtered INTO a signal.
#
# CAVEAT, Crystal Palace: their site returns CloudFront 403 to everything, homepage included,
# which is edge blocking rather than a missing feed and is known to trigger on datacenter/VPN
# addresses. Re-probe from a residential connection before concluding they have none.
OFFICIAL_FEEDS = {
    "Aston Villa": ("https://www.avfc.co.uk/rss.xml", "Latest News - Aston Villa FC"),
    "Bournemouth": ("https://www.afcb.co.uk/rss.xml", "Latest News - AFC Bournemouth"),
    "Brighton": ("https://www.brightonandhovealbion.com/rss", "Brighton & Hove Albion"),
    "Coventry City": ("https://www.ccfc.co.uk/rss.xml", "Latest News - Coventry City FC"),
    "Everton": ("https://www.evertonfc.com/rss.xml", "Latest News - Everton"),
    "Fulham": ("https://www.fulhamfc.com/rss.xml", "Latest News - Fulham FC"),
    "Ipswich": ("https://www.itfc.co.uk/rss.xml", "Latest News - Ipswich Town"),
    "Ipswich Town": ("https://www.itfc.co.uk/rss.xml", "Latest News - Ipswich Town"),
    "Nott'm Forest": ("https://www.nottinghamforest.co.uk/rss.xml",
                      "Latest News - Nottingham Forest FC"),
    "Sunderland": ("https://www.safc.com/rss.xml", "Latest News - Sunderland AFC"),
}


# The Premier League's own content API. The ONLY route to the eleven clubs that publish no feed
# of their own, because the league republishes its clubs' material under a per-club tag — so
# reaching their words needs one endpoint rather than eleven scrapers (§31).
#
# Slugs follow no single convention and are not guessable: Bournemouth is `afc-bournemouth`, and
# Brighton is `brighton-&-hove-albion` WITH AN AMPERSAND, which is why every hyphenated variant
# of it returns nothing. The `&` must be percent-encoded or it terminates the query string, which
# `Source.url` does for this source kind.
PL_CONTENT_API = ("https://footballapi.pulselive.com/content/PremierLeague/text/EN/"
                  "?pageSize=40&page=0&tagNames=club-produced-content:{slug}")
PL_CLUB_TAG = "club-produced-content:"

PL_SLUGS = {
    "Arsenal": "arsenal",
    "Aston Villa": "aston-villa",
    "Bournemouth": "afc-bournemouth",
    "Brentford": "brentford",
    "Brighton": "brighton-&-hove-albion",           # ampersand, not a hyphen
    "Burnley": "burnley",
    "Chelsea": "chelsea",
    "Coventry City": "coventry-city",
    "Crystal Palace": "crystal-palace",
    "Everton": "everton",
    "Fulham": "fulham",
    "Hull City": "hull-city",
    "Ipswich": "ipswich-town",
    "Ipswich Town": "ipswich-town",
    "Leeds": "leeds-united",
    "Leicester": "leicester-city",
    "Liverpool": "liverpool",
    "Man City": "manchester-city",
    "Man Utd": "manchester-united",
    "Newcastle": "newcastle-united",
    "Nott'm Forest": "nottingham-forest",
    "Sheffield Utd": "sheffield-united",
    "Spurs": "tottenham-hotspur",
    "Sunderland": "sunderland",
    "West Ham": "west-ham-united",
    "Wolves": "wolverhampton-wanderers",
}

KIND_RSS = "rss"
KIND_PL = "pl"


@dataclass(frozen=True)
class Source:
    """One publisher's per-club feeds.

    `feeds` maps a club to either a slug (rendered through `template`) or, when `template` is the
    identity, a whole URL. `titles` is the channel title each feed must announce, and is None
    only where the publisher does not provide a distinguishing one. `kind` selects the reader,
    because not every publisher speaks RSS.
    """

    name: str
    feeds: Mapping[str, str]
    template: str = "{slug}"
    titles: Mapping[str, str] | None = None
    kind: str = KIND_RSS

    def url(self, club: str) -> str:
        slug = self.feeds[club]
        if self.kind == KIND_PL:
            # Brighton's slug contains `&`; unencoded it would end the query string and the tag
            # filter would silently not apply — which returns other clubs' items, not an error.
            slug = quote(slug, safe="")
        return self.template.format(slug=slug)

    def expected_title(self, club: str) -> str | None:
        return (self.titles or {}).get(club)


def _split(table: Mapping[str, tuple[str, str]]) -> tuple[dict, dict]:
    return ({k: v[0] for k, v in table.items()}, {k: v[1] for k, v in table.items()})


_G_FEEDS, _G_TITLES = _split(GUARDIAN_FEEDS)
_O_FEEDS, _O_TITLES = _split(OFFICIAL_FEEDS)

SOURCES: tuple[Source, ...] = (
    # BBC announces "BBC Sport" as the channel title on every club feed, so there is nothing to
    # verify against — its guard is that a wrong slug 404s, which was confirmed by probing.
    Source("bbc", BBC_SLUGS, BBC_TEAM_FEED, None),
    Source("guardian", _G_FEEDS, GUARDIAN_TEAM_FEED, _G_TITLES),
    Source("official", _O_FEEDS, "{slug}", _O_TITLES),
    # Guarded per item instead of by a channel title, because JSON has no channel.
    Source("pl", PL_SLUGS, PL_CONTENT_API, None, KIND_PL),
)


def sources_for(club: str, sources: tuple[Source, ...] = SOURCES) -> list[Source]:
    """Every configured source that covers this club. May be empty."""
    return [s for s in sources if club in s.feeds]


def clubs_in_play(bootstrap: dict) -> tuple[list[str], list[str]]:
    """The clubs actually in the league this season, from the FPL bootstrap. (known, unknown).

    ALWAYS derive the league from here rather than from a feed table. The bootstrap is the
    authority on who is in the division; the tables are only name-to-URL lookups and may contain
    clubs who are not currently up, or lack one who is.

    "Known" means at least one source covers the club. Sources are additive — Brighton has no
    Guardian tag and eleven clubs publish no feed of their own, and neither is a problem. A club
    covered by NOTHING is, and it is returned in `unknown` rather than skipped so the caller can
    fail loudly: such a club contributes no team news for a whole season while every other signal
    looks healthy.
    """
    names = sorted(t["name"] for t in bootstrap.get("teams", []))
    known = [n for n in names if sources_for(n)]
    unknown = [n for n in names if not sources_for(n)]
    return known, unknown


def coverage(clubs: list[str]) -> dict[str, list[str]]:
    """source name -> the clubs it covers, for reporting how thin each publisher's reach is."""
    return {s.name: [c for c in clubs if c in s.feeds] for s in SOURCES}


MIN_INTERVAL_S = 1.0


class NewsFeedError(RuntimeError):
    pass


def _text(node, tag: str) -> str:
    el = node.find(tag)
    return unescape((el.text or "").strip()) if el is not None and el.text else ""


def _norm_title(text: str) -> str:
    """Compare channel titles forgivingly on case and spacing, strictly on everything else."""
    return re.sub(r"\s+", " ", (text or "")).strip().casefold()


_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def strip_html(text: str) -> str:
    """Feed descriptions are escaped HTML at every publisher except BBC — `<p>`, links, the lot.

    `_text` unescapes once, which turns `&lt;p&gt;` into a real tag; this removes the tags and
    unescapes again for entities that were double-escaped underneath them. Tags become spaces
    rather than nothing, so `</p><p>` cannot weld two sentences into one word.
    """
    return _WS.sub(" ", unescape(_TAG.sub(" ", text or ""))).strip()


def parse_feed(xml_text: str) -> tuple[str, list[dict]]:
    """RSS 2.0 -> (channel title, items). Raises on malformed XML rather than returning nothing.

    An empty item list is a legitimate answer (a quiet club), so a parse failure must NOT produce
    one — the two would be indistinguishable in the index and a broken feed would read as a quiet
    week for the rest of the season.

    The channel title comes back because for some publishers it is the only thing that
    distinguishes this club's feed from the site-wide one; see GUARDIAN_FEEDS.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise NewsFeedError(f"malformed RSS: {exc}") from exc
    channel = root.find("channel")
    title = _text(channel, "title") if channel is not None else ""
    out = []
    for item in root.iter("item"):
        out.append({
            "guid": _text(item, "guid") or _text(item, "link"),
            "title": strip_html(_text(item, "title")),
            "summary": strip_html(_text(item, "description")),
            "link": _text(item, "link"),
            "published": _text(item, "pubDate"),
        })
    return title, out


def parse_rss(xml_text: str) -> list[dict]:
    """Just the items. `parse_feed` when the channel title matters."""
    return parse_feed(xml_text)[1]


def parse_pl_content(json_text: str, slug: str) -> list[dict]:
    """The Premier League content API -> items, keeping only those tagged for this club.

    THE SAME QUIET FAILURE AS THE GUARDIAN'S, IN A DIFFERENT WIRE FORMAT. An unrecognised
    `tagNames` value is not rejected — the API ignores the filter and answers HTTP 200 with a
    perfectly valid page of OTHER clubs' articles. Asking for `not-a-club` returns ten items
    spread across five real clubs. So the guard cannot live at the request layer; every item is
    checked for the club tag it was supposed to be filtered by, and anything else is dropped.

    Getting only foreign items back means the filter did not apply, and the response therefore
    says nothing about whether this club is quiet. That is an error rather than an empty list:
    additive sources mean the club falls back to its other feeds, which is the right outcome, and
    a wrong slug stays loud instead of reading as a quiet week.
    """
    try:
        payload = json.loads(json_text)
    except ValueError as exc:
        raise NewsFeedError(f"malformed JSON: {exc}") from exc

    wanted = f"{PL_CLUB_TAG}{slug}"
    out, foreign = [], 0
    for entry in payload.get("content") or []:
        labels = {t.get("label") for t in (entry.get("tags") or []) if isinstance(t, dict)}
        if wanted not in labels:
            foreign += 1
            continue
        out.append({
            # Namespaced so a numeric id cannot collide with an RSS guid in the corpus dedupe.
            "guid": f"pl:{entry.get('id')}",
            "title": strip_html(entry.get("title") or ""),
            "summary": strip_html(entry.get("summary") or entry.get("description") or ""),
            # `canonicalUrl` is empty on every item; `hotlinkUrl` is the real article, and it
            # points at the club's own site — which is the point of this source.
            "link": entry.get("hotlinkUrl") or "",
            "published": entry.get("date") or "",     # ISO-8601 here, RFC-822 in the RSS sources
        })
    if foreign and not out:
        raise NewsFeedError(
            f"tag {wanted!r} matched nothing but {foreign} other clubs' items came back — "
            "the filter was ignored, so this response is not evidence about this club")
    return out


class NewsFeedClient:
    """Polite reader for publisher RSS across several sources. No article bodies are fetched."""

    # Transport failures per source before the rest of the run skips it. A publisher whose
    # host is HANGING (not erroring) costs a full timeout per attempt per club; without a
    # breaker, 20 clubs x 2 attempts x 20s against one dead publisher is ~13 minutes of wall
    # clock — past the capture Lambda's ceiling, which kills the run before land() and loses
    # every club already fetched. Two strikes bounds that at ~80s, and the skip is recorded
    # as a per-source partial failure, so coverage accounting stays honest.
    MAX_TRANSPORT_FAILURES = 2

    def __init__(self, session=None, min_interval: float | None = None,
                 sources: tuple[Source, ...] = SOURCES):
        import requests

        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": config.HTTP_USER_AGENT})
        self._timeout = config.HTTP_TIMEOUT
        self._min_interval = MIN_INTERVAL_S if min_interval is None else min_interval
        self._last = 0.0
        self.sources = sources
        self._transport_failures: dict[str, int] = {}

    def _throttle(self) -> None:
        dt = time.monotonic() - self._last
        if dt < self._min_interval:
            time.sleep(self._min_interval - dt)
        self._last = time.monotonic()

    def fetch(self, source: Source, club: str) -> list[dict]:
        """One club from one publisher. Raises rather than returning an empty list on any doubt."""
        import requests

        fails = self._transport_failures.get(source.name, 0)
        if fails >= self.MAX_TRANSPORT_FAILURES:
            raise NewsFeedError(
                f"{club}/{source.name}: skipped — {fails} transport failures already this run"
            )
        url = source.url(club)
        try:
            # The throttle runs as `before_attempt` so retried attempts respect the politeness
            # interval too; attempts=2 keeps the worst case per fetch to ~2 timeouts, which is
            # what the breaker's arithmetic above assumes.
            resp = get_with_retries(self.session, url, timeout=self._timeout,
                                    attempts=2, before_attempt=self._throttle)
        except requests.RequestException as exc:
            # A transport failure MUST become a NewsFeedError: `club()` treats NewsFeedError as
            # "this publisher failed, the club keeps its other sources", and any other exception
            # type escapes that catch and crashes the whole capture — with every club already
            # fetched this run still unlanded. One timed-out feed cost a full day's corpus once.
            self._transport_failures[source.name] = fails + 1
            raise NewsFeedError(
                f"{club}/{source.name}: {type(exc).__name__} from {urlparse(url).netloc}"
            ) from exc
        if resp.status_code != 200:
            raise NewsFeedError(
                f"{club}/{source.name}: HTTP {resp.status_code} from {urlparse(url).netloc}")
        if source.kind == KIND_PL:
            # Guarded per item rather than per feed — see `parse_pl_content`. The raw slug is
            # compared, not the percent-encoded one that went into the URL.
            try:
                items = parse_pl_content(resp.text, source.feeds[club])
            except NewsFeedError as exc:
                raise NewsFeedError(f"{club}/{source.name}: {exc}") from exc
            return [{**it, "club": club, "source": source.name} for it in items]
        title, items = parse_feed(resp.text)
        expected = source.expected_title(club)
        if expected is not None and _norm_title(title) != _norm_title(expected):
            # Not pedantry: a wrong Guardian slug serves the site-wide football feed under a 200
            # with twenty valid items, so this is the ONLY thing standing between a typo and a
            # season of league-wide news filed as one club's team news.
            raise NewsFeedError(
                f"{club}/{source.name}: feed announces {title!r}, expected {expected!r} — "
                f"this feed is not about {club}; the slug is wrong or the publisher renamed it")
        return [{**it, "club": club, "source": source.name} for it in items]

    def club(self, club: str, *, failures: list | None = None) -> list[dict]:
        """Recent items for one club from every source that covers it, tagged with both.

        Sources are additive, so a publisher that fails costs coverage rather than the club: the
        items from the others are still returned and the failure is appended to `failures`. Only
        when EVERY source for the club fails does this raise — at that point the club really is
        silent, and silence must never pass for a quiet week.
        """
        configured = sources_for(club, self.sources)
        if not configured:
            raise NewsFeedError(f"no feed slug for {club!r}")
        items: list[dict] = []
        errors: list[dict] = []
        for source in configured:
            try:
                items.extend(self.fetch(source, club))
            except NewsFeedError as exc:
                errors.append({"club": club, "source": source.name, "error": str(exc)})
        if errors and not items:
            raise NewsFeedError("; ".join(e["error"] for e in errors))
        if failures is not None:
            failures.extend(errors)
        return items


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
