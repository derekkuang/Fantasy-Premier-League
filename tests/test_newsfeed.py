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
    GUARDIAN_FEEDS,
    KIND_PL,
    OFFICIAL_FEEDS,
    NewsFeedClient,
    NewsFeedError,
    Source,
    cue_tags,
    mentions,
    normalise,
    parse_feed,
    parse_rss,
    sources_for,
    strip_html,
)

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Arsenal | The Guardian</title>
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
    def __init__(self, text=RSS, status=200, by_url=None):
        self.headers: dict = {}
        self.calls: list = []
        self._text, self._status = text, status
        self._by_url = by_url or {}       # substring -> (text, status), for per-source behaviour

    def get(self, url, timeout=None):
        self.calls.append(url)
        for needle, (text, status) in self._by_url.items():
            if needle in url:
                return _Resp(text, status)
        return _Resp(self._text, self._status)


def _feed(title: str, n: int = 2) -> str:
    items = "".join(
        f"<item><title>Item {i}</title><description>d{i}</description>"
        f"<guid>g{i}</guid></item>" for i in range(n)
    )
    return f'<?xml version="1.0"?><rss version="2.0"><channel>' \
           f"<title>{title}</title>{items}</channel></rss>"


# One source, no title guard — the shape the original single-source tests assumed.
BBC_ONLY = (Source("bbc", {"Arsenal": "arsenal"}, "https://bbc.test/{slug}.xml", None),)


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
    c = NewsFeedClient(session=_Session(), min_interval=0, sources=BBC_ONLY)
    got = c.club("Arsenal")
    assert all(i["club"] == "Arsenal" and i["source"] == "bbc" for i in got)


def test_a_non_200_raises_so_a_dead_club_feed_cannot_pass_as_quiet():
    c = NewsFeedClient(session=_Session(status=404), min_interval=0, sources=BBC_ONLY)
    with pytest.raises(NewsFeedError, match="404"):
        c.club("Arsenal")


def test_an_unknown_club_raises_rather_than_guessing_a_slug():
    c = NewsFeedClient(session=_Session(), min_interval=0)
    with pytest.raises(NewsFeedError, match="no feed slug"):
        c.club("Real Madrid")


# --- several sources per club --------------------------------------------------------------- #
TWO = (
    Source("bbc", {"Arsenal": "arsenal"}, "https://bbc.test/{slug}.xml", None),
    Source("guardian", {"Arsenal": "arsenal"}, "https://grauniad.test/{slug}/rss",
           {"Arsenal": "Arsenal | The Guardian"}),
)


def test_every_source_covering_a_club_is_fetched_and_tagged():
    sess = _Session(by_url={
        "bbc.test": (_feed("BBC Sport", 2), 200),
        "grauniad.test": (_feed("Arsenal | The Guardian", 3), 200),
    })
    got = NewsFeedClient(session=sess, min_interval=0, sources=TWO).club("Arsenal")
    assert len(got) == 5
    assert {i["source"] for i in got} == {"bbc", "guardian"}


def test_one_dead_source_costs_coverage_but_not_the_club():
    """Sources are additive. A publisher going down must not take the club's other feeds with
    it, or one flaky site silently blanks a club that three others are still covering."""
    sess = _Session(by_url={
        "bbc.test": (_feed("BBC Sport", 2), 200),
        "grauniad.test": ("", 503),
    })
    failures: list = []
    got = NewsFeedClient(session=sess, min_interval=0, sources=TWO).club(
        "Arsenal", failures=failures)
    assert [i["source"] for i in got] == ["bbc", "bbc"]
    assert len(failures) == 1 and failures[0]["source"] == "guardian" and "503" in failures[0][
        "error"]


def test_a_club_raises_only_when_every_source_fails():
    sess = _Session(status=500)
    with pytest.raises(NewsFeedError):
        NewsFeedClient(session=sess, min_interval=0, sources=TWO).club("Arsenal")


def test_a_timed_out_source_costs_coverage_but_not_the_club():
    """THE CRASH THIS PREVENTS. `club()` catches NewsFeedError, but a slow publisher raises
    requests.Timeout — which is not one. Before the wrap in `fetch`, one timed-out feed escaped
    the per-source catch and crashed the entire capture, with every already-fetched club's items
    still unlanded: the partial-failure design held for HTTP errors and not for the most common
    real-world failure there is."""
    import requests

    sess = _Session(by_url={"bbc.test": (_feed("BBC Sport", 2), 200)})
    orig = sess.get

    def get(url, timeout=None):
        if "grauniad.test" in url:
            raise requests.ConnectTimeout("publisher hung")
        return orig(url, timeout=timeout)

    sess.get = get
    failures: list = []
    got = NewsFeedClient(session=sess, min_interval=0, sources=TWO).club(
        "Arsenal", failures=failures)
    assert [i["source"] for i in got] == ["bbc", "bbc"]
    assert len(failures) == 1 and "ConnectTimeout" in failures[0]["error"]


def test_a_repeatedly_hanging_publisher_is_skipped_for_the_rest_of_the_run():
    """THE WALL-CLOCK CEILING. A hanging (not erroring) publisher costs a full timeout per
    attempt per club; 20 clubs against one dead host is ~13 minutes — past the capture
    Lambda's limit, which kills the run before land() and loses every club already fetched.
    After MAX_TRANSPORT_FAILURES strikes the source is skipped instantly for remaining clubs,
    recorded as a partial failure per club so coverage accounting stays honest."""
    import requests

    THREE_CLUBS = (
        Source("bbc", {"Arsenal": "arsenal", "Chelsea": "chelsea", "Everton": "everton"},
               "https://bbc.test/{slug}.xml", None),
        Source("guardian", {"Arsenal": "arsenal", "Chelsea": "chelsea", "Everton": "everton"},
               "https://grauniad.test/{slug}/rss",
               {"Arsenal": "g", "Chelsea": "g", "Everton": "g"}),
    )
    sess = _Session(by_url={"grauniad.test": (_feed("g", 1), 200)})
    bbc_calls: list = []
    orig = sess.get

    def get(url, timeout=None):
        if "bbc.test" in url:
            bbc_calls.append(url)
            raise requests.ConnectTimeout("host hangs")
        return orig(url, timeout=timeout)

    sess.get = get
    client = NewsFeedClient(session=sess, min_interval=0, sources=THREE_CLUBS)
    failures: list = []
    for club in ("Arsenal", "Chelsea", "Everton"):
        got = client.club(club, failures=failures)
        assert [i["source"] for i in got] == ["guardian"], f"{club} keeps its other source"
    # Two clubs' worth of real attempts (2 each with retries), then the breaker: Everton's
    # BBC fetch never touches the network.
    assert len(bbc_calls) == 4
    assert len(failures) == 3
    assert "skipped" in failures[2]["error"]


def test_a_feed_serving_the_site_wide_edition_is_rejected():
    """THE BUG THIS GUARD EXISTS TO PREVENT, and it is invisible to every other check. An
    unrecognised Guardian slug does not 404 — it answers HTTP 200 with twenty well-formed items
    from the site-wide football feed. A typo would file league-wide news as one club's team news,
    and it would look HEALTHIER than a genuinely quiet club because it carries more items. Status
    code, parse success and item count all say fine; only the channel title disagrees."""
    sess = _Session(by_url={
        "bbc.test": (_feed("BBC Sport", 2), 200),
        "grauniad.test": (_feed("Football | The Guardian", 20), 200),   # the site-wide feed
    })
    failures: list = []
    got = NewsFeedClient(session=sess, min_interval=0, sources=TWO).club(
        "Arsenal", failures=failures)
    assert [i["source"] for i in got] == ["bbc", "bbc"]      # the 20 impostors are not in here
    assert "not about Arsenal" in failures[0]["error"]


def test_the_title_guard_forgives_case_and_spacing_only():
    sess = _Session(by_url={"grauniad.test": (_feed("  arsenal   |  THE guardian ", 2), 200),
                            "bbc.test": ("", 404)})
    got = NewsFeedClient(session=sess, min_interval=0, sources=TWO).club("Arsenal")
    assert len(got) == 2


def test_a_source_without_a_distinguishing_title_is_not_guarded():
    """BBC announces "BBC Sport" on every club feed, so there is nothing to check it against —
    its protection is that a wrong slug 404s. The guard must be optional, not assumed."""
    sess = _Session(by_url={"bbc.test": (_feed("BBC Sport", 2), 200)})
    got = NewsFeedClient(session=sess, min_interval=0, sources=BBC_ONLY).club("Arsenal")
    assert len(got) == 2


# --- richer feeds carry HTML ---------------------------------------------------------------- #
def test_html_is_stripped_from_descriptions():
    """Every source except BBC embeds markup. Left in, it becomes the bulk of the "text" an
    extraction pass reads and it poisons whole-word name matching."""
    xml = ('<?xml version="1.0"?><rss><channel><title>T</title><item>'
           "<title>Saka fit</title>"
           "<description>&lt;p&gt;Arteta said &lt;a href=\"/x\"&gt;Saka&lt;/a&gt; trained.&lt;/p&gt;"
           "&lt;p&gt;He is available.&lt;/p&gt;</description>"
           "</item></channel></rss>")
    assert parse_rss(xml)[0]["summary"] == "Arteta said Saka trained. He is available."


def test_tags_become_spaces_so_adjacent_sentences_do_not_weld_together():
    assert strip_html("<p>ruled out</p><p>Saka starts</p>") == "ruled out Saka starts"


def test_a_stripped_summary_still_matches_player_names():
    """Inline markup (<b> around a surname) must not hide a player from the matcher — that is
    the failure mode that would make the richest sources match the fewest players."""
    item = {"club": "Arsenal", "title": "",
            "summary": strip_html("<p>Mikel Arteta confirmed <b>Bukayo Saka</b> is fit.</p>")}
    assert [m["element_id"] for m in mentions(item, PLAYERS)] == [1]


def test_parse_feed_returns_the_channel_title():
    title, items = parse_feed(RSS)
    assert title == "Arsenal | The Guardian"
    assert len(items) == 2


def test_the_slug_table_is_a_lookup_not_a_league():
    """It used to assert exactly twenty entries, which is what encoded "this list IS the Premier
    League" and let three relegated clubs sit in it while three promoted ones were missing. The
    table should hold MORE clubs than any one season needs; the bootstrap decides who is up."""
    assert len(BBC_SLUGS) > 20
    # Two do not follow BBC's obvious pattern and 404 on the naive guess.
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


# --- the league is not a constant ---------------------------------------------------------- #
def _boot(names):
    return {"teams": [{"id": i, "name": n} for i, n in enumerate(names, 1)]}


def test_the_league_comes_from_the_bootstrap_not_from_the_slug_table():
    """THE BUG THIS EXISTS TO PREVENT. The first version hardcoded twenty clubs and called that
    the Premier League. Three had been relegated and three promoted ones were missing, so three
    clubs contributed NO team news all season while the run reported "20/20 clubs" — it was
    counting its own wrong list. League composition changes every year; it is never a constant."""
    from fpledge.ingest.newsfeed import clubs_in_play

    known, unknown = clubs_in_play(_boot(["Arsenal", "Coventry City", "Hull City"]))
    assert known == ["Arsenal", "Coventry City", "Hull City"]
    assert unknown == []


def test_a_club_with_no_slug_is_returned_rather_than_silently_dropped():
    """A promoted club with no slug is silent for a whole season and every other signal looks
    healthy. The caller has to be able to stop, so it must not be filtered away here."""
    from fpledge.ingest.newsfeed import clubs_in_play

    known, unknown = clubs_in_play(_boot(["Arsenal", "Some New Club"]))
    assert known == ["Arsenal"]
    assert unknown == ["Some New Club"]


def test_relegated_clubs_stay_in_the_lookup_but_are_not_in_the_league():
    """Keeping them costs nothing and means a promotion needs no code change — but they must
    only appear when the bootstrap says they are up."""
    from fpledge.ingest.newsfeed import BBC_SLUGS, clubs_in_play

    assert "Wolves" in BBC_SLUGS and "West Ham" in BBC_SLUGS
    known, _ = clubs_in_play(_boot(["Arsenal", "Leeds"]))
    assert "Wolves" not in known and "West Ham" not in known


def test_every_club_the_bootstrap_might_name_has_a_slug():
    """Both short and full forms, because FPL has used each ('Ipswich' and 'Ipswich Town')."""
    from fpledge.ingest.newsfeed import BBC_SLUGS

    for name in ("Ipswich", "Ipswich Town", "Coventry City", "Hull City", "Sunderland", "Leeds"):
        assert name in BBC_SLUGS, name


# --- the source tables ---------------------------------------------------------------------- #
def test_a_club_is_covered_when_any_single_source_has_it():
    """Sources are additive, so coverage is a union. Brighton is the live example: the Guardian
    has no tag for them at all and their own site carries them."""
    assert "Brighton" not in GUARDIAN_FEEDS
    assert "Brighton" in OFFICIAL_FEEDS
    assert [s.name for s in sources_for("Brighton")] == ["bbc", "official", "pl"]
    # Arsenal is the mirror image: no feed of their own, covered by the other three.
    assert [s.name for s in sources_for("Arsenal")] == ["bbc", "guardian", "pl"]


def test_a_club_no_source_covers_is_reported_rather_than_dropped():
    known, unknown = clubs_in_play_(["Arsenal", "Some New Club"])
    assert known == ["Arsenal"] and unknown == ["Some New Club"]


def test_partial_source_coverage_is_never_treated_as_a_missing_club():
    """Eleven clubs publish no feed of their own and one has no Guardian tag. If thin coverage
    counted as "unknown", the capture would abort every run over a condition that is normal."""
    known, unknown = clubs_in_play_(["Brighton", "Arsenal", "Liverpool"])
    assert unknown == []
    assert set(known) == {"Brighton", "Arsenal", "Liverpool"}


def test_coverage_reports_each_publishers_reach():
    from fpledge.ingest.newsfeed import coverage

    got = coverage(["Arsenal", "Brighton"])
    assert got["bbc"] == ["Arsenal", "Brighton"]
    assert got["guardian"] == ["Arsenal"]        # no Brighton tag exists
    assert got["official"] == ["Brighton"]       # Arsenal publish no feed


def test_every_configured_feed_declares_the_title_it_must_announce():
    """A Guardian or official entry without an expected title is an unguarded feed, and an
    unguarded Guardian feed is exactly how the site-wide edition gets in."""
    for club, (slug, title) in GUARDIAN_FEEDS.items():
        assert slug and title.endswith("| The Guardian"), club
    for club, (url, title) in OFFICIAL_FEEDS.items():
        assert url.startswith("https://") and title, club


def test_name_aliases_point_at_the_same_feed():
    assert GUARDIAN_FEEDS["Ipswich"] == GUARDIAN_FEEDS["Ipswich Town"]
    assert OFFICIAL_FEEDS["Ipswich"] == OFFICIAL_FEEDS["Ipswich Town"]


def clubs_in_play_(names):
    from fpledge.ingest.newsfeed import clubs_in_play

    return clubs_in_play(_boot(names))


# --- the Premier League content API (JSON, not RSS) ------------------------------------------ #
def _pl(*clubs_and_titles) -> str:
    """A PL content payload. Each arg is (club-slug, title)."""
    import json as _json

    return _json.dumps({"content": [
        {"id": 100 + i, "title": t, "summary": f"<p>summary of {t}</p>",
         "hotlinkUrl": f"https://club.test/{i}", "date": "2026-08-10T18:05:00Z",
         "tags": [{"label": f"club-produced-content:{slug}"}, {"label": "content-type:article"}]}
        for i, (slug, t) in enumerate(clubs_and_titles)
    ]})


PL_ONE = (Source("pl", {"Arsenal": "arsenal"},
                 "https://pl.test/?tagNames=club-produced-content:{slug}", None, KIND_PL),)


def test_pl_items_are_parsed_and_tagged():
    sess = _Session(_pl(("arsenal", "Saka fit"), ("arsenal", "Rice out")))
    got = NewsFeedClient(session=sess, min_interval=0, sources=PL_ONE).club("Arsenal")
    assert [i["title"] for i in got] == ["Saka fit", "Rice out"]
    assert all(i["source"] == "pl" and i["club"] == "Arsenal" for i in got)
    assert got[0]["summary"] == "summary of Saka fit"          # HTML stripped
    assert got[0]["link"] == "https://club.test/0"             # hotlinkUrl, not canonicalUrl
    assert got[0]["guid"] == "pl:100"                          # namespaced against RSS guids


def test_a_tag_filter_that_failed_open_is_rejected_not_returned():
    """THE GUARDIAN BUG IN JSON. An unknown `tagNames` is not an error — the API ignores the
    filter and answers 200 with a valid page of OTHER clubs' articles. Asking for a club and
    receiving five other clubs' items must never read as 'this club is quiet'."""
    sess = _Session(_pl(("chelsea", "a"), ("everton", "b"), ("brentford", "c")))
    with pytest.raises(NewsFeedError, match="filter was ignored"):
        NewsFeedClient(session=sess, min_interval=0, sources=PL_ONE).club("Arsenal")


def test_foreign_items_are_dropped_when_some_of_ours_come_back():
    sess = _Session(_pl(("arsenal", "ours"), ("chelsea", "theirs")))
    got = NewsFeedClient(session=sess, min_interval=0, sources=PL_ONE).club("Arsenal")
    assert [i["title"] for i in got] == ["ours"]


def test_an_empty_pl_response_is_a_quiet_club_not_an_error():
    """Zero items with zero foreign ones means the filter DID apply and found nothing."""
    sess = _Session('{"content": []}')
    assert NewsFeedClient(session=sess, min_interval=0, sources=PL_ONE).club("Arsenal") == []


def test_malformed_pl_json_raises_rather_than_returning_nothing():
    sess = _Session("{not json")
    with pytest.raises(NewsFeedError, match="malformed JSON"):
        NewsFeedClient(session=sess, min_interval=0, sources=PL_ONE).club("Arsenal")


def test_brightons_ampersand_slug_is_percent_encoded_in_the_url():
    """Unencoded, the `&` ends the query string and the tag filter silently does not apply —
    which returns other clubs' items rather than an error. Brighton is the only club affected
    and the only one where a naive f-string would quietly poison the bucket."""
    from fpledge.ingest.newsfeed import PL_SLUGS, SOURCES

    pl = next(s for s in SOURCES if s.kind == KIND_PL)
    assert PL_SLUGS["Brighton"] == "brighton-&-hove-albion"
    assert "%26" in pl.url("Brighton") and "&-hove" not in pl.url("Brighton")


def test_the_pl_source_covers_the_clubs_the_other_sources_cannot():
    """The whole reason it was added: eleven clubs publish no feed of their own."""
    from fpledge.ingest.newsfeed import OFFICIAL_FEEDS, PL_SLUGS

    for club in ("Arsenal", "Liverpool", "Man Utd", "Chelsea", "Spurs", "Newcastle"):
        assert club not in OFFICIAL_FEEDS and club in PL_SLUGS, club
    assert "Brighton" in PL_SLUGS          # and the one the Guardian has no tag for
