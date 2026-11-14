"""Which stories reach the team-news page: team news, and nothing else (HANDOFF §39).

The page used to show the six newest items per club and block known junk (women's and youth
sides, tickets, the programme). A blocklist always misses the next thing: the Christmas bear's
name, the shop sale, the stadium tour. So this keeps only what an FPL manager can act on:

  a story is TEAM NEWS when its HEADLINE carries an availability or selection signal
  (injury, suspension, return, team news / line-up / press conference, a manager change)
  AND it is about the first team: it names a current player from that club, it is a
  team-news piece, or it is a manager change.

Whole words only, in the headline only. The old keyword cues matched fragments anywhere in the
text ("rest" in "Forest", "ban" in "urban") and agreed with FPL about a quarter of the time.
Anything about women's or youth sides is dropped even if a name matches, because names collide
(Lauren James is not Reece James).

On 14 Nov 2026 this kept 8 of 120 stories, all of them real team news.

FOUR LEAKS, found on the live page the day it shipped (HANDOFF §39), and closed here:
  * the same manager change, three or four times over: a club keeps its newest manager story;
  * a manager story filed under the wrong club (a Guardian piece about Man Utd's manager,
    tagged Aston Villa because Villa were the opponents): it must name its club in the headline;
  * Guardian columns, letters and podcasts ("... | Jonathan Wilson"): never news;
  * women's sides whose club site never says "Women": Chelsea's and Brighton's women's head
    coaches publish on the same feed as the men's, so they are named in `WOMENS_HEAD_COACHES`.

FPL's own flags are the other half of the page: `flagged_players` lists everyone FPL marks
doubtful, injured or suspended, straight from the bootstrap, so the page is complete even when
no feed has written about a player yet.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from functools import cache

from fpledge.ingest.newsfeed import GUARDIAN_FEEDS


def _words(*patterns: str) -> re.Pattern:
    return re.compile(r"\b(" + "|".join(patterns) + r")\b", re.IGNORECASE)


# Headline signals, by the label the page shows.
SIGNALS: dict[str, re.Pattern] = {
    "Injury": _words(
        r"injur(y|ies|ed)", "knock", r"strain(ed)?", "hamstring", "ankle", "groin", "calf", "thigh",
        "knee", "illness", "surgery", "operation", "scan", "sidelined", "ruled out",
        r"withdr(aws?|awn|ew)", r"doubt(ful)?", "setback", r"fitness (test|update|concern|doubt|blow)", "concussion", r"fracture[ds]?",
        "unavailable", r"absen(t|ce)", "will miss", "misses", "out for"),
    "Suspension": _words(r"suspen(ded|sion)", r"ban(ned)?", "red card", "sent off", "appeal",
                         r"yellow cards?"),
    "Return": _words(r"returns?", "back in training", "fit again", "back from injury", "recovered",
                     "in contention", "available again"),
    "Team news": _words("team news", r"line-?up", r"starting (xi|eleven)", "press conference",
                        r"rotat(e|ion)", "rested", "squad news"),
    # Not a bare "appointed": that is also a chief executive or a sporting director.
    "Manager": _words(r"sack(ed|s)?", r"appointed (as )?(new )?(head coach|manager|boss)",
                      r"new (head coach|manager|boss)", "interim", "parted company"),
}
# A piece that is team news by its format, whether or not it names anyone.
TEAM_NEWS_FORMAT = _words("team news", "press conference", r"line-?up", "starting xi",
                          "injury update", "fitness update")
# Never the first team, whatever names it matches.
NOT_FIRST_TEAM = _words(r"women('s)?", r"wsl2?", r"u1[5-9]s?", r"u2[0-3]s?", r"under-?\d\d",
                        "academy", "pl2", "youth cup", "lionesses", "players cup")
# Women's head coaches whose club's feed carries their pressers and injury news without ever
# saying "Women" ("Sonia Bompastor provides injury update on Buchanan and Malard"; "Albion v
# Liverpool | Ruiz & Symonds pre-match press conference"). The feeds carry no category to tell
# them apart, so they are named, per club, from what the corpus showed on 14 Nov 2026. Other
# women's sides say "Women" or "WSL" and are caught above. When a coach changes, change this.
WOMENS_HEAD_COACHES = {"Chelsea": _words("Bompastor"), "Brighton": _words("Ruiz")}

# A club as headlines write it. The full names are the Guardian's (its channel titles); these
# are the short forms the FPL name and the full name both miss.
_CLUB_EXTRA = {
    "Man Utd": ("Man United", "Manchester Utd"), "Spurs": ("Tottenham",),
    "Nott'm Forest": ("Forest",), "Crystal Palace": ("Palace",), "Aston Villa": ("Villa",),
    "Brighton": ("Albion", "Brighton & Hove Albion"), "Wolves": ("Wolverhampton",),
    "Hull City": ("Hull",), "Coventry City": ("Coventry",), "Ipswich Town": ("Ipswich",),
    "Bournemouth": ("AFC Bournemouth", "Cherries"),
}

FLAG_STATUSES = ("d", "i", "s")       # doubtful, injured, suspended; "u" is mostly loans and exits
POSITION = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def _plain(text: str) -> str:
    """Curly apostrophes and quotes straightened, so "Tel’s" matches "Tel"."""
    return (text or "").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')


def squads(labels: Mapping[int, Mapping]) -> dict[str, list[tuple[int, str]]]:
    """{club: [(element_id, name to look for)]} from `fpl_labels`. "N.Jackson" is looked for as
    "Jackson"; names under three letters are skipped (too many collisions)."""
    out: dict[str, list[tuple[int, str]]] = {}
    for el, lab in labels.items():
        name = (lab.get("name") or "").split(".")[-1].strip()
        if lab.get("team") and len(name) >= 3:
            out.setdefault(lab["team"], []).append((el, name))
    return out


def headline_players(title: str, club: str, club_squads: Mapping[str, Iterable[tuple[int, str]]]) -> list[int]:
    """Players from `club` named in the headline, whole word."""
    t = _plain(title)
    return [el for el, name in club_squads.get(club, ())
            if re.search(rf"(?<![\w'-]){re.escape(name)}(?![\w-])", t)]


@cache
def _club_names(club: str) -> re.Pattern:
    names = {club, *_CLUB_EXTRA.get(club, ())}
    if club in GUARDIAN_FEEDS:
        names.add(GUARDIAN_FEEDS[club][1].split(" | ")[0])
    return re.compile(r"(?<![\w'])(" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
                      + r")(?![\w])", re.IGNORECASE)


def names_club(title: str, club: str) -> bool:
    """Whether the headline names `club`, in any of the ways headlines do."""
    return bool(club) and bool(_club_names(club).search(_plain(title)))


def team_news(item: Mapping, club_squads: Mapping) -> tuple[list[str], list[int]] | None:
    """(labels, headline players) if the story is team news, otherwise None."""
    title = _plain(item.get("title") or "")
    club = item.get("club") or ""
    if NOT_FIRST_TEAM.search(f"{title} {_plain(item.get('summary') or '')}"):
        return None
    coach = WOMENS_HEAD_COACHES.get(club)
    if coach is not None and coach.search(title):
        return None
    # The Guardian titles its columns, letters and podcasts "Headline | Author"; its news never.
    if item.get("source") == "guardian" and " | " in title:
        return None
    labels = [label for label, rx in SIGNALS.items() if rx.search(title)]
    # A manager change is news about the club the headline names, not the club whose feed it
    # came through: "Carrick denies risk of Manchester United sack" reached Aston Villa's.
    if "Manager" in labels and not names_club(title, club):
        labels.remove("Manager")
    if not labels:
        return None
    players = headline_players(title, club, club_squads)
    if players or TEAM_NEWS_FORMAT.search(title) or "Manager" in labels:
        return labels, players
    return None


def flagged_players(bootstrap: Mapping) -> list[dict]:
    """Everyone FPL marks doubtful, injured or suspended, most-owned first, in FPL's own words."""
    teams = {t["id"]: t["name"] for t in bootstrap.get("teams", [])}
    out = []
    for e in bootstrap.get("elements", []):
        if e.get("status") not in FLAG_STATUSES:
            continue
        out.append({
            "element_id": e["id"],
            "name": e.get("web_name"),
            "team": teams.get(e.get("team")),
            "position": POSITION.get(e.get("element_type"), ""),
            "status": e["status"],
            "chance": e.get("chance_of_playing_next_round"),
            "news": (e.get("news") or "").strip(),
            "news_added": e.get("news_added"),
            "ownership": float(e.get("selected_by_percent") or 0),
        })
    return sorted(out, key=lambda p: (-p["ownership"], p["name"] or ""))


_STOP = {"the", "a", "an", "and", "of", "to", "in", "on", "for", "with", "by", "as", "at", "is",
         "after", "his", "her", "their", "from", "be", "has", "have", "how", "what", "why", "bbc",
         "sport"}


def headline_words(title: str) -> frozenset[str]:
    return frozenset(w for w in re.findall(r"[a-z0-9]+", _plain(title).lower()) if w not in _STOP)


def same_story(a: frozenset[str], b: frozenset[str]) -> bool:
    """One outlet's "Carrick sacked by Manchester United" and another's "Michael Carrick sacked
    by Manchester United with Pochettino poised..." are one story: nearly all of the shorter
    headline's words are in the longer one. Three-word headlines and shorter never merge."""
    small, big = (a, b) if len(a) <= len(b) else (b, a)
    return len(small) >= 3 and len(small & big) / len(small) >= 0.8
