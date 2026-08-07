"""Club news feeds: parsing, player matching, and the ways a capture can lie quietly.

No network — a fake session replays a real BBC payload shape. The failure this capture is most
likely to suffer is a club feed 404ing silently: that club then has no team news all season and
nothing in the output would say so, which is why several tests below are about noise rather than
correctness.
"""

from __future__ import annotations

import pytest

from fpledge.ingest.newsfeed import (
    BBC_SLUGS,
    NewsFeedClient,
    NewsFeedError,
    cue_tags,
    mentions,
    normalise,
    parse_rss,
)

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>Arsenal have 'big hopes' for Saka - Arteta</title>
    <description>Mikel Arteta says Bukayo Saka trained fully and is available.</description>
    <link>https://www.bbc.co.uk/sport/football/1</link>
    <guid>urn:bbc:1</guid>
    <pubDate>Fri, 07 Aug 2026 10:07:00 GMT</pubDate>
  </item>
  <item>
    <title>Injury blow as Rice ruled out</title>
    <description>Declan Rice is sidelined with a hamstring strain.</description>
    <link>https://www.bbc.co.uk/sport/football/2</link>
    <guid>urn:bbc:2</guid>
  </item>
</channel></rss>"""

PLAYERS = [
    {"element_id": 1, "web_name": "Saka", "full_name": "Bukayo Saka", "team": "Arsenal"},
    {"element_id": 2, "web_name": "Rice", "full_name": "Declan Rice", "team": "Arsenal"},
    {"element_id": 3, "web_name": "Salah", "full_name": "Mohamed Salah", "team": "Liverpool"},
    {"element_id": 4, "web_name": "Sels", "full_name": "Matz Sels", "team": "Nott'm Forest"},
]


class _Resp:
    def __init__(self, text, status=200):
        self.text, self.status_code = text, status


class _Session:
    def __init__(self, text=RSS, status=200):
        self.headers: dict = {}
        self.calls: list = []
        self._text, self._status = text, status

    def get(self, url, timeout=None):
        self.calls.append(url)
        return _Resp(self._text, self._status)


# --- parsing ------------------------------------------------------------------------------ #
def test_items_parse_with_the_fields_extraction_will_need():
    items = parse_rss(RSS)
    assert len(items) == 2
    assert items[0]["guid"] == "urn:bbc:1"
    assert "Saka" in items[0]["title"]
    assert "trained fully" in items[0]["summary"]
    assert items[0]["published"].startswith("Fri, 07 Aug")


def test_malformed_xml_raises_rather_than_returning_no_items():
    """An empty list is a legitimate answer — a quiet club. A parse failure must not be
    indistinguishable from one, or a broken feed reads as a quiet week all season."""
    with pytest.raises(NewsFeedError, match="malformed"):
        parse_rss("<rss><channel><item><title>unclosed")


def test_a_feed_with_no_items_is_empty_not_an_error():
    assert parse_rss('<?xml version="1.0"?><rss><channel></channel></rss>') == []


# --- the client --------------------------------------------------------------------------- #
def test_items_are_tagged_with_their_club_and_source():
    c = NewsFeedClient(session=_Session(), min_interval=0)
    got = c.club("Arsenal")
    assert all(i["club"] == "Arsenal" and i["source"] == "bbc" for i in got)


def test_a_non_200_raises_so_a_dead_club_feed_cannot_pass_as_quiet():
    c = NewsFeedClient(session=_Session(status=404), min_interval=0)
    with pytest.raises(NewsFeedError, match="404"):
        c.club("Arsenal")


def test_an_unknown_club_raises_rather_than_guessing_a_slug():
    c = NewsFeedClient(session=_Session(), min_interval=0)
    with pytest.raises(NewsFeedError, match="no feed slug"):
        c.club("Real Madrid")


def test_every_premier_league_club_has_a_slug():
    """Two clubs do not follow BBC's obvious pattern and 404 on the naive guess. A missing slug
    means that club never contributes team news."""
    assert len(BBC_SLUGS) == 20
    assert BBC_SLUGS["Bournemouth"] == "afc-bournemouth"
    assert BBC_SLUGS["Brighton"] == "brighton-and-hove-albion"


# --- player matching ---------------------------------------------------------------------- #
def test_a_named_player_is_matched_by_web_name_and_full_name():
    items = [{**i, "club": "Arsenal"} for i in parse_rss(RSS)]
    assert [m["name"] for m in mentions(items[0], PLAYERS)] == ["Saka"]
    assert [m["name"] for m in mentions(items[1], PLAYERS)] == ["Rice"]


def test_matching_never_crosses_clubs():
    """The Understat join's rule, for the same reason: an item on the Arsenal feed cannot be
    about Liverpool's player, and two players share a surname."""
    item = {"club": "Arsenal", "title": "Salah in top form", "summary": ""}
    assert mentions(item, PLAYERS) == []


def test_short_names_do_not_match_inside_other_words():
    """"Sels" inside "vessels" is the failure mode that makes every short surname noise."""
    item = {"club": "Nott'm Forest", "title": "Blood vessels and assels", "summary": ""}
    assert mentions(item, PLAYERS) == []


def test_a_player_named_twice_is_reported_once():
    item = {"club": "Arsenal", "title": "Saka and Saka again", "summary": "Bukayo Saka"}
    assert len(mentions(item, PLAYERS)) == 1


def test_normalisation_strips_punctuation_and_case():
    assert normalise("Arteta's BIG hopes!") == "arteta s big hopes"


# --- intent cues -------------------------------------------------------------------------- #
def test_cues_flag_injury_and_return_and_rotation():
    assert "injury" in cue_tags({"title": "Rice ruled out", "summary": "hamstring strain"})
    assert "return" in cue_tags({"title": "", "summary": "he trained fully and is available"})
    assert "rotation" in cue_tags({"title": "Arteta to make changes", "summary": ""})
    assert "suspension" in cue_tags({"title": "banned for three games", "summary": ""})


def test_cues_are_empty_when_nothing_matches():
    assert cue_tags({"title": "Club announces new kit", "summary": "sponsor deal"}) == []
