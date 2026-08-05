"""Expected saves from shots faced.

Almost every test here is about a DIRECTION. Saves data is symmetric in shape — two teams,
two counts per match — so getting the attribution backwards produces numbers of exactly the
right magnitude attached to the wrong team, which no plausibility check catches. The shot-zone
orientation bug in `ingest.understat` was the same class of error and survived until someone
went looking, so these assertions are deliberately explicit about whose keeper is whose.
"""

from __future__ import annotations

from fpledge.models.saves import (
    DEFAULT_LEAGUE_MEAN,
    SavesRates,
    TeamSaveCounts,
    accumulate,
    saves_by_match,
)


# --- deriving counts from shot events ---------------------------------------------------- #
def test_a_saved_home_shot_is_a_save_by_the_AWAY_keeper():
    """The inversion that matters. A shot the home side took and the keeper saved was saved by
    the away keeper — attributing it to the home keeper credits the wrong team all season."""
    shots = [
        {"match_id": "1", "side": "h", "result": "SavedShot"},
        {"match_id": "1", "side": "h", "result": "SavedShot"},
        {"match_id": "1", "side": "a", "result": "SavedShot"},
    ]
    assert saves_by_match(shots)["1"] == {"h": 1, "a": 2}


def test_only_saved_shots_count_as_saves():
    """Blocked shots are stopped by an outfield player and missed shots never reached the
    target; neither earns a save point, so neither may inflate the rate."""
    shots = [
        {"match_id": "1", "side": "h", "result": "SavedShot"},
        {"match_id": "1", "side": "h", "result": "BlockedShot"},
        {"match_id": "1", "side": "h", "result": "MissedShots"},
        {"match_id": "1", "side": "h", "result": "Goal"},
        {"match_id": "1", "side": "h", "result": "ShotOnPost"},
    ]
    assert saves_by_match(shots)["1"] == {"h": 0, "a": 1}


def test_matches_with_no_saves_are_absent_rather_than_zero():
    assert saves_by_match([{"match_id": "1", "side": "h", "result": "Goal"}]) == {}


# --- accumulation ------------------------------------------------------------------------ #
def test_accumulate_splits_faced_from_forced():
    counts: dict = {}
    accumulate(counts, home_id=1, away_id=2, home_keeper_saves=5, away_keeper_saves=2)
    assert counts[1].faced == 5 and counts[1].forced == 2      # home keeper made 5
    assert counts[2].faced == 2 and counts[2].forced == 5      # away keeper made 2
    assert counts[1].matches_faced == 1 and counts[2].matches_faced == 1


def test_accumulate_is_additive_across_matches():
    counts: dict = {}
    accumulate(counts, 1, 2, 5, 2)
    accumulate(counts, 2, 1, 1, 3)     # reverse fixture: team 2 at home
    assert counts[1].faced == 5 + 3
    assert counts[1].matches_faced == 2


# --- rates and shrinkage ------------------------------------------------------------------ #
def _counts(spec):
    """spec: {team: (faced, forced, matches)}"""
    return {
        t: TeamSaveCounts(faced=f, forced=fo, matches_faced=m, matches_forced=m)
        for t, (f, fo, m) in spec.items()
    }


def test_league_mean_is_saves_per_team_match():
    rates = SavesRates.build(_counts({1: (30, 30, 10), 2: (10, 10, 10)}))
    assert rates.league_mean == 2.0        # 40 saves over 20 team-matches


def test_a_thin_sample_is_shrunk_hard_toward_the_league_mean():
    """One match at 10 saves is not a 10-saves-per-match defence. With a 4-match prior the
    reported rate must sit far closer to the mean than to the observation."""
    counts = _counts({1: (10, 10, 1), 2: (30, 30, 15), 3: (30, 30, 15)})
    rates = SavesRates.build(counts)
    busy = rates.expected_saves(team_id=1, opp_id=3, x_minutes=90)
    assert busy < 4.0                       # nowhere near the raw 10
    assert busy > rates.league_mean         # but still above average


def test_more_evidence_shrinks_less():
    thin = SavesRates.build(_counts({1: (10, 4, 1), 2: (8, 8, 20), 3: (8, 8, 20)}))
    thick = SavesRates.build(_counts({1: (100, 40, 10), 2: (80, 80, 20), 3: (80, 80, 20)}))
    assert (
        thick.expected_saves(1, 3, 90) > thin.expected_saves(1, 3, 90)
    )


def test_a_busier_keeper_and_a_sharper_opponent_both_raise_the_estimate():
    counts = _counts({1: (60, 20, 20), 2: (20, 60, 20), 3: (40, 40, 20)})
    rates = SavesRates.build(counts)
    # team 1 concedes a lot of saves; team 2 forces a lot of them
    assert rates.expected_saves(1, 2, 90) > rates.expected_saves(1, 3, 90)
    assert rates.expected_saves(1, 3, 90) > rates.expected_saves(3, 3, 90)


def test_an_unknown_team_contributes_a_neutral_factor_not_a_zero():
    """A promoted side has no history. Treating that as zero would hand every keeper facing
    them a spotless projection, which is worse than admitting we know nothing."""
    rates = SavesRates.build(_counts({1: (40, 40, 20), 2: (40, 40, 20)}))
    assert rates.expected_saves(team_id=99, opp_id=98, x_minutes=90) == rates.league_mean


def test_expected_saves_scales_linearly_with_minutes():
    rates = SavesRates.build(_counts({1: (40, 40, 20), 2: (40, 40, 20)}))
    full = rates.expected_saves(1, 2, 90)
    assert rates.expected_saves(1, 2, 45) == full / 2
    assert rates.expected_saves(1, 2, 0) == 0.0


def test_no_history_falls_back_to_the_default_mean():
    rates = SavesRates.build({})
    assert rates.league_mean == DEFAULT_LEAGUE_MEAN
