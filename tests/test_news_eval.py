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
