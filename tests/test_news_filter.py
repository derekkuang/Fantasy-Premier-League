"""Team news only (fpledge/news_filter.py, HANDOFF §39). Cases are real headlines from 14 Nov 2026."""

from __future__ import annotations

from fpledge.eval.news_eval import DIGEST_WINDOW_DAYS, build_digest
from fpledge.news_filter import (
    flagged_players,
    headline_players,
    headline_words,
    same_story,
    squads,
    team_news,
)

LABELS = {
    1: {"name": "Tel", "team": "Spurs", "status": "d", "news": "Ankle injury - 50% chance of playing", "flagged": True},
    2: {"name": "Manzambi", "team": "Aston Villa", "status": "d", "news": "Calf injury - 75% chance of playing", "flagged": True},
    3: {"name": "James", "team": "Chelsea", "status": "i", "news": "Hamstring injury", "flagged": True},
    4: {"name": "Thiago", "team": "Brentford", "status": "s", "news": "Suspended until 5 Dec", "flagged": True},
    5: {"name": "N.Jackson", "team": "Aston Villa", "status": "a", "news": "", "flagged": False},
    6: {"name": "Gibbs-White", "team": "Nott'm Forest", "status": "a", "news": "", "flagged": False},
}
SQUADS = squads(LABELS)


def story(club, title, summary=""):
    return {"club": club, "title": title, "summary": summary}


# --- what counts as team news ----------------------------------------------------------- #
def test_a_named_player_with_an_injury_headline_is_kept_with_its_label():
    got = team_news(story("Aston Villa", "BBC Sport: Manzambi withdraws from Switzerland squad with injury"), SQUADS)
    assert got == (["Injury"], [2])


def test_curly_apostrophes_and_short_names_still_match():
    """Tel was missed before: the old matcher skipped names under four letters."""
    got = team_news(story("Spurs", "De Zerbi offers latest on Tel’s ‘bad injury on the ankle’"), SQUADS)
    assert got == (["Injury"], [1])


def test_the_mascot_and_the_shop_are_not_team_news():
    for title in ("Our Christmas Bear’s name is revealed", "30% off Third Kit at The Cov Store",
                  "Festive stadium tours and Legends Tours on sale", "Jackson named PL Player of the Month!"):
        assert team_news(story("Aston Villa", title), SQUADS) is None, title


def test_womens_and_youth_stories_are_dropped_even_when_a_name_collides():
    """Lauren James is not Reece James."""
    s = story("Chelsea", "Bompastor updates on James and Girma availability ahead of Man City",
              "Chelsea Women head coach Sonia Bompastor gave an update...")
    assert team_news(s, SQUADS) is None
    assert team_news(story("Fulham", "U18: injury blow ahead of FA Youth Cup tie"), SQUADS) is None


def test_team_news_pieces_and_manager_changes_need_no_name():
    assert team_news(story("Spurs", "See Spurs' starting line-up to face Leeds"), SQUADS) == (["Team news"], [])
    assert team_news(story("Crystal Palace", "Crystal Palace sack boss Sage after 16 games"), SQUADS) == (["Manager"], [])


def test_signals_are_whole_words_in_the_headline_only():
    """The old cues matched "rest" in Forest and anything in the summary."""
    assert team_news(story("Nott'm Forest", "Gibbs-White on Forest's interest in a title push"), SQUADS) is None
    assert team_news(story("Spurs", "Tel scores twice", "He had been ruled out with injury last month"), SQUADS) is None


def test_a_name_from_another_club_is_not_a_match():
    assert headline_players("Tel injury update", "Aston Villa", SQUADS) == []
    assert headline_players("Jackson ruled out", "Aston Villa", SQUADS) == [5]   # "N.Jackson" -> "Jackson"


# --- FPL's own flags ------------------------------------------------------------------------ #
def test_flagged_players_are_doubtful_injured_or_suspended_most_owned_first():
    boot = {
        "teams": [{"id": 1, "name": "Spurs"}],
        "elements": [
            {"id": 1, "web_name": "Tel", "team": 1, "element_type": 4, "status": "d", "chance_of_playing_next_round": 50,
             "news": "Ankle injury - 50% chance of playing", "news_added": "2026-11-12T10:00:00Z", "selected_by_percent": "3.1"},
            {"id": 7, "web_name": "Solanke", "team": 1, "element_type": 4, "status": "i", "chance_of_playing_next_round": 0,
             "news": "Knee injury - Unknown return date", "news_added": None, "selected_by_percent": "12.0"},
            {"id": 8, "web_name": "Loanee", "team": 1, "element_type": 3, "status": "u", "news": "Joined X on loan",
             "selected_by_percent": "0.1"},
            {"id": 9, "web_name": "Fit", "team": 1, "element_type": 2, "status": "a", "news": "", "selected_by_percent": "40"},
        ],
    }
    got = flagged_players(boot)
    assert [p["name"] for p in got] == ["Solanke", "Tel"]
    assert got[1] == {"element_id": 1, "name": "Tel", "team": "Spurs", "position": "FWD", "status": "d", "chance": 50,
                      "news": "Ankle injury - 50% chance of playing", "news_added": "2026-11-12T10:00:00Z", "ownership": 3.1}


# --- the digest in the page's mode --------------------------------------------------------- #
def test_the_page_digest_keeps_last_weeks_team_news_with_fpls_view_beside_it():
    now = "2026-11-14T18:00:00+00:00"
    items = [
        {**story("Spurs", "De Zerbi offers latest on Tel’s ‘bad injury on the ankle’"), "source": "bbc",
         "published": "Fri, 13 Nov 2026 10:00:00 GMT", "link": "https://x/1"},
        {**story("Spurs", "Tel ruled out of the Leeds game"), "source": "bbc",
         "published": "Wed, 04 Nov 2026 10:00:00 GMT", "link": "https://x/2"},       # 10 days old
        {**story("Aston Villa", "Our Christmas Bear’s name is revealed"), "source": "official",
         "published": "Fri, 13 Nov 2026 10:00:00 GMT", "link": "https://x/3"},
    ]
    d = build_digest(items, LABELS, now, team_news_only=True, bootstrap={"teams": [], "elements": []})
    assert list(d["clubs"]) == ["Spurs"] and len(d["clubs"]["Spurs"]) == 1
    entry = d["clubs"]["Spurs"][0]
    assert entry["labels"] == ["Injury"]
    assert entry["players"] == [{"element_id": 1, "name": "Tel", "fpl_status": "d",
                                 "fpl_news": "Ankle injury - 50% chance of playing"}]
    assert d["window_days"] == DIGEST_WINDOW_DAYS
    assert d["filter"] == {"considered": 2, "kept": 1, "injury_stories_naming_players": 1, "agree_with_fpl": 1}
    assert d["flagged"] == []


def test_the_same_story_in_different_words_is_one_story():
    a = headline_words("Carrick sacked by Manchester United")
    b = headline_words("Michael Carrick sacked by Manchester United with Pochettino poised to take over")
    assert same_story(a, b)
    # different stories that share a club name and a word or two stay apart
    assert not same_story(headline_words("TEAM NEWS | AFC BOURNEMOUTH"),
                          headline_words("Team News: Four changes for Liverpool test"))
    assert not same_story(headline_words("Team news"), headline_words("Team news: two changes"))


def test_the_page_digest_merges_reworded_copies_and_keeps_both_sources():
    items = [
        {**story("Man Utd", "Carrick sacked by Manchester United"), "source": "bbc",
         "published": "Thu, 12 Nov 2026 11:42:00 GMT", "link": "https://a/1"},
        {**story("Man Utd", "Michael Carrick sacked by Manchester United with Pochettino poised to take over"),
         "source": "guardian", "published": "Thu, 12 Nov 2026 10:28:00 GMT", "link": "https://b/2"},
    ]
    d = build_digest(items, LABELS, "2026-11-14T18:00:00+00:00", team_news_only=True, bootstrap={})
    (entry,) = d["clubs"]["Man Utd"]
    assert entry["sources"] == ["bbc", "guardian"] and entry["labels"] == ["Manager"]


def test_fitness_counts_only_as_a_fitness_test_or_update():
    assert team_news(story("Spurs", "Tel faces fitness test before Arsenal"), SQUADS) == (["Injury"], [1])
    assert team_news(story("Spurs", "Fitness, Tel and a back four: what next for Spurs"), SQUADS) is None

