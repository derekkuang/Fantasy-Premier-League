"""Scoring the news extractor against FPL's own field.

The point of these tests is the ASYMMETRY between the three numbers. Precision and recall are
scored against a partial oracle — FPL's field is itself derived from press conferences, so a
disagreement may be our error or a signal they have not published yet. The additive set is the
only one that carries commercial weight, and it is the one most likely to be quietly wrong,
because it is defined by an ABSENCE in FPL's data rather than a presence in ours.
"""

from __future__ import annotations

from fpledge.eval.news_eval import evaluate, fpl_labels


def _labels():
    return fpl_labels({
        "teams": [{"id": 1, "name": "Arsenal"}, {"id": 2, "name": "Chelsea"}],
        "elements": [
            {"id": 10, "web_name": "Saliba", "team": 1, "status": "i",
             "news": "Back injury - Unknown return date"},
            {"id": 11, "web_name": "Saka", "team": 1, "status": "a", "news": ""},
            {"id": 12, "web_name": "Palmer", "team": 2, "status": "a", "news": ""},
            {"id": 13, "web_name": "Tosin", "team": 2, "status": "d",
             "news": "Knock - 75% chance of playing"},
        ],
    })


def _item(club, mentions, cues):
    return {"club": club, "guid": f"g{mentions}{cues}",
            "mentions": [{"element_id": e} for e in mentions], "cues": cues}


def test_a_status_flag_or_news_text_both_count_as_flagged():
    """FPL uses both: a player can carry news with status 'a', or a status with no text."""
    lab = fpl_labels({"teams": [{"id": 1, "name": "A"}], "elements": [
        {"id": 1, "web_name": "x", "team": 1, "status": "a", "news": "Knock"},
        {"id": 2, "web_name": "y", "team": 1, "status": "i", "news": ""},
        {"id": 3, "web_name": "z", "team": 1, "status": "a", "news": ""},
    ]})
    assert lab[1]["flagged"] and lab[2]["flagged"] and not lab[3]["flagged"]


def test_precision_counts_only_injury_and_suspension_cues():
    """A rotation cue is not a claim that anyone is injured, so it must not be scored as one —
    that would make precision look worse for the category we most want to keep."""
    items = [_item("Arsenal", [10], ["injury"]), _item("Arsenal", [11], ["rotation"])]
    res = evaluate(items, _labels())
    assert res["precision"]["flagged_by_feed"] == 1
    assert res["precision"]["confirmed_by_fpl"] == 1
    assert res["precision"]["rate"] == 1.0


def test_an_unconfirmed_injury_claim_is_named_not_just_counted():
    """The dangerous direction. Acting on "X is out" when he is fit is worse than knowing
    nothing, because the projection acts on it — so these have to be inspectable."""
    items = [_item("Arsenal", [11], ["injury"])]        # Saka, whom FPL does not flag
    res = evaluate(items, _labels())
    assert res["precision"]["rate"] == 0.0
    assert [u["name"] for u in res["precision"]["unconfirmed"]] == ["Saka"]


def test_recall_is_over_players_fpl_flags_not_over_items():
    items = [_item("Arsenal", [10], ["injury"])]        # names 1 of the 2 flagged players
    res = evaluate(items, _labels())
    assert res["recall"]["fpl_flagged"] == 2
    assert res["recall"]["mentioned_by_feed"] == 1
    assert res["recall"]["rate"] == 0.5


def test_a_mention_with_no_cue_still_counts_for_recall():
    """Recall asks whether the SOURCE saw the player at all — it is a property of the feed, not
    of our cue vocabulary. Requiring a cue would blame the extractor for the source's silence."""
    items = [_item("Arsenal", [10], [])]
    assert evaluate(items, _labels())["recall"]["mentioned_by_feed"] == 1


def test_additive_excludes_anyone_fpl_already_flags():
    """The whole commercial case is signal FPL does NOT publish. A rotation cue on a player they
    already flag is worth nothing and must not inflate the number that justifies spending."""
    items = [_item("Chelsea", [13], ["rotation"]),     # Tosin — FPL flags him
             _item("Chelsea", [12], ["rotation"])]     # Palmer — FPL says nothing
    res = evaluate(items, _labels())
    assert res["additive"]["count"] == 1
    assert res["additive"]["players"][0]["name"] == "Palmer"


def test_cues_accumulate_across_items_for_the_same_player():
    """Two articles, one naming an injury and one a return, describe one player's situation."""
    items = [_item("Arsenal", [10], ["injury"]), _item("Arsenal", [10], ["return"])]
    res = evaluate(items, _labels())
    assert res["n_players_mentioned"] == 1
    assert res["precision"]["flagged_by_feed"] == 1


def test_an_empty_corpus_reports_none_rather_than_dividing_by_zero():
    res = evaluate([], _labels())
    assert res["precision"]["rate"] is None
    assert res["additive"]["count"] == 0
    assert res["recall"]["rate"] == 0.0


def test_the_digest_drops_clubs_that_left_the_league():
    """The corpus is cumulative and outlives a season. Without the current-league filter a
    relegated club keeps appearing months after it went down — which is how the page came to
    report 23 clubs in a 20-team league."""
    from fpledge.eval.news_eval import build_digest

    items = [
        {"club": "Arsenal", "title": "a", "published": "x", "cues": [], "mentions": []},
        {"club": "Wolves", "title": "b", "published": "x", "cues": [], "mentions": []},
    ]
    d = build_digest(items, _labels(), "now", clubs_allowed=["Arsenal"])
    assert list(d["clubs"]) == ["Arsenal"]
    assert d["n_clubs"] == 1


def test_without_an_allowlist_every_club_is_kept():
    """Analysis over a historical corpus should see relegated clubs; only the PAGE filters."""
    from fpledge.eval.news_eval import build_digest

    items = [
        {"club": "Arsenal", "title": "a", "published": "x", "cues": [], "mentions": []},
        {"club": "Wolves", "title": "b", "published": "x", "cues": [], "mentions": []},
    ]
    assert build_digest(items, _labels(), "now")["n_clubs"] == 2


# --- ordering and length, once feeds carry real volume --------------------------------------- #
def _row(club, title, published, summary="", source="bbc"):
    return {"club": club, "title": title, "published": published, "summary": summary,
            "source": source, "mentions": [], "cues": []}


def test_published_dates_are_parsed_not_string_compared():
    """THE BUG THIS EXISTS TO PREVENT. Every source emits RFC-822, so a reverse STRING sort
    orders by weekday name — 'Fri, 05 Jun' beats 'Mon, 10 Aug'. It hid while BBC gave four items
    per club and there was nothing to choose between; at sixty items per club it meant the
    "newest six" on the page were six arbitrary ones, some of them months old."""
    from fpledge.eval.news_eval import build_digest

    items = [
        _row("Arsenal", "june", "Fri, 05 Jun 2026 14:00:00 GMT"),
        _row("Arsenal", "august", "Mon, 10 Aug 2026 09:00:00 GMT"),
        _row("Arsenal", "july", "Sun, 05 Jul 2026 09:00:00 GMT"),
    ]
    got = build_digest(items, _labels(), "now")["clubs"]["Arsenal"]
    assert [i["title"] for i in got] == ["august", "july", "june"]


def test_an_undated_item_sorts_last_rather_than_first():
    """A missing date is not evidence of freshness, and this page's whole value is currency."""
    from fpledge.eval.news_eval import build_digest

    items = [_row("Arsenal", "undated", ""),
             _row("Arsenal", "dated", "Mon, 10 Aug 2026 09:00:00 GMT")]
    got = build_digest(items, _labels(), "now")["clubs"]["Arsenal"]
    assert [i["title"] for i in got] == ["dated", "undated"]


def test_an_unparseable_date_does_not_crash_the_digest():
    from fpledge.eval.news_eval import build_digest, parse_published

    assert parse_published("not a date") is None
    items = [_row("Arsenal", "junk", "not a date"),
             _row("Arsenal", "good", "Mon, 10 Aug 2026 09:00:00 GMT")]
    assert [i["title"] for i in build_digest(items, _labels(), "now")["clubs"]["Arsenal"]] == [
        "good", "junk"]


def test_long_summaries_are_shortened_for_the_page_on_a_word_boundary():
    """A club's own feed runs to 5,000 chars per item; six of those is an article, not a digest."""
    from fpledge.eval.news_eval import DIGEST_SUMMARY_CHARS, build_digest

    long = "Arteta confirmed the squad is fit and available for selection " * 40
    got = build_digest([_row("Arsenal", "t", "Mon, 10 Aug 2026 09:00:00 GMT", long)],
                       _labels(), "now")["clubs"]["Arsenal"][0]["summary"]
    assert len(got) <= DIGEST_SUMMARY_CHARS + 1        # +1 for the ellipsis
    assert got.endswith("…") and not got.endswith(" …")
    assert "availabl…" not in got                      # never mid-word


def test_a_short_summary_is_left_exactly_as_it_is():
    from fpledge.eval.news_eval import build_digest

    got = build_digest([_row("Arsenal", "t", "Mon, 10 Aug 2026 09:00:00 GMT", "Saka is fit.")],
                       _labels(), "now")["clubs"]["Arsenal"][0]["summary"]
    assert got == "Saka is fit."


def test_truncation_is_display_only_and_never_touches_the_corpus():
    """The corpus is the extraction input. Shortening it there would throw away the very text
    the richer sources were added to capture."""
    from fpledge.eval.news_eval import build_digest

    long = "x " * 500
    items = [_row("Arsenal", "t", "Mon, 10 Aug 2026 09:00:00 GMT", long)]
    build_digest(items, _labels(), "now")
    assert items[0]["summary"] == long


def test_the_digest_records_which_publisher_each_item_came_from():
    """Three sources of very different quality now feed one page; a reader who cannot tell a
    club's own statement from a rumour column cannot weigh either."""
    from fpledge.eval.news_eval import build_digest

    items = [_row("Arsenal", "t", "Mon, 10 Aug 2026 09:00:00 GMT", source="official")]
    assert build_digest(items, _labels(), "now")["clubs"]["Arsenal"][0]["source"] == "official"


def test_both_date_formats_parse_because_the_sources_disagree():
    """RSS emits RFC-822, the Premier League's JSON emits ISO-8601. Reading only the first would
    not raise — it would return None for every PL item, sorting the richest source permanently
    last so it never reached the page."""
    from fpledge.eval.news_eval import parse_published

    rfc = parse_published("Mon, 10 Aug 2026 09:48:53 GMT")
    iso = parse_published("2026-08-10T18:05:00Z")
    offset = parse_published("2026-08-11T14:00:00+0100")
    assert rfc is not None and iso is not None and offset is not None
    assert iso > rfc                                    # same day, later hour, comparable
    assert offset.utcoffset().total_seconds() == 0      # normalised to UTC, never naive


def test_the_two_formats_interleave_correctly_in_the_digest():
    from fpledge.eval.news_eval import build_digest

    items = [_row("Arsenal", "rss-older", "Mon, 10 Aug 2026 09:00:00 GMT"),
             _row("Arsenal", "json-newer", "2026-08-10T18:05:00Z", source="pl"),
             _row("Arsenal", "rss-oldest", "Sun, 09 Aug 2026 09:00:00 GMT")]
    got = build_digest(items, _labels(), "now")["clubs"]["Arsenal"]
    assert [i["title"] for i in got] == ["json-newer", "rss-older", "rss-oldest"]
