"""The Understat identity join and shot-zone aggregation.

The join is the highest-risk code in the project because its failures are silent — a
mis-matched player attributes one man's shots to another and every downstream number stays
plausible. So these tests are mostly about what the join REFUSES to do.

No network here: the `fetch_*` adapters are thin wrappers over soccerdata and are exercised
separately (see the module docstring), while everything that can silently corrupt data is
pure and tested exhaustively.
"""

from __future__ import annotations

from fpledge.ingest.understat import (
    MIN_SHOTS_FOR_SHARE,
    build_fpl_id_map,
    coverage,
    normalise_name,
    shot_zone,
    surname,
    zone_shares,
)


# --- name normalisation ----------------------------------------------------------------- #
def test_accents_and_punctuation_are_stripped():
    assert normalise_name("Ødegaard") == "odegaard"   # Ø does NOT decompose under NFKD
    assert normalise_name("Håland") == "haland"
    assert normalise_name("Bałka") == "balka"
    assert normalise_name("N'Golo Kanté") == "ngolo kante"
    assert normalise_name("Son Heung-min") == "son heung min"
    assert normalise_name("  Van  Dijk ") == "van dijk"


def test_normalisation_is_stable_on_empty_input():
    assert normalise_name("") == ""
    assert normalise_name(None) == ""
    assert surname("") == ""


def test_surname_takes_the_last_token():
    assert surname("Son Heung-min") == "min"     # documents the known limit, see below
    assert surname("Virgil van Dijk") == "dijk"


# --- the join ---------------------------------------------------------------------------- #
FPL = [
    {"element_id": 1, "full_name": "Bukayo Saka", "web_name": "Saka", "team": "Arsenal"},
    {"element_id": 2, "full_name": "Gabriel Martinelli", "web_name": "Martinelli", "team": "Arsenal"},
    {"element_id": 3, "full_name": "Gabriel Magalhaes", "web_name": "Gabriel", "team": "Arsenal"},
    {"element_id": 4, "full_name": "Mohamed Salah", "web_name": "M.Salah", "team": "Liverpool"},
    {"element_id": 5, "full_name": "Diogo Jota", "web_name": "Jota", "team": "Liverpool"},
]


def _u(uid, name, team):
    return {"understat_id": uid, "name": name, "team": team}


def test_exact_name_within_the_club_matches():
    rep = build_fpl_id_map(FPL, [_u("u1", "Bukayo Saka", "Arsenal")])
    assert rep["map"] == {"u1": 1}
    assert rep["matched_by"]["u1"] == "exact"


def test_accented_source_name_still_matches():
    rep = build_fpl_id_map(
        [{"element_id": 9, "full_name": "Martin Odegaard", "team": "Arsenal"}],
        [_u("u1", "Martin Ødegaard", "Arsenal")],
    )
    assert rep["map"] == {"u1": 9}


def test_surname_only_source_matches_when_unique_at_the_club():
    """Understat carries "Salah"; FPL has full_name "Mohamed Salah" and web_name "M.Salah",
    so neither alias matches exactly and the surname fallback is what joins them."""
    rep = build_fpl_id_map(FPL, [_u("u1", "Salah", "Liverpool")])
    assert rep["map"] == {"u1": 4}
    assert rep["matched_by"]["u1"] == "surname"


def test_never_matches_across_teams():
    """The whole guard rail: a name that exists at another club is NOT a match. Without this,
    every transfer window silently reassigns a player's history to his old club's namesake."""
    rep = build_fpl_id_map(FPL, [_u("u1", "Mohamed Salah", "Arsenal")])
    assert rep["map"] == {}
    assert [u["understat_id"] for u in rep["unmatched"]] == ["u1"]


def test_single_name_player_matches_on_web_name():
    """Two Gabriels at Arsenal, and Understat calls the defender just "Gabriel" — which is
    exactly FPL's web_name for him. Matching aliases resolves it without guessing."""
    rep = build_fpl_id_map(FPL, [_u("u1", "Gabriel", "Arsenal")])
    assert rep["map"] == {"u1": 3}
    assert rep["matched_by"]["u1"] == "exact"


def test_a_genuinely_ambiguous_first_name_refuses_to_guess():
    """Strip the distinguishing web_name and there is no basis to choose between the two
    Gabriels — the join must report it rather than pick one."""
    no_alias = [dict(p) for p in FPL]
    for p in no_alias:
        p.pop("web_name", None)
    rep = build_fpl_id_map(no_alias, [_u("u1", "Gabriel", "Arsenal")])
    assert rep["map"] == {}
    assert [u["understat_id"] for u in rep["unmatched"] + rep["ambiguous"]] == ["u1"]


def test_an_alias_sharing_a_surname_is_not_read_as_two_players():
    """"Bukayo Saka" and "Saka" are one man indexed twice; a naive count makes that ambiguous
    and silently drops a top asset from every downstream feature."""
    rep = build_fpl_id_map(FPL, [_u("u1", "Saka", "Arsenal")])
    assert rep["map"] == {"u1": 1}


def test_duplicate_full_names_at_one_club_are_ambiguous():
    dupes = [
        {"element_id": 10, "full_name": "Danny Ward", "team": "Leicester"},
        {"element_id": 11, "full_name": "Danny Ward", "team": "Leicester"},
    ]
    rep = build_fpl_id_map(dupes, [_u("u1", "Danny Ward", "Leicester")])
    assert rep["map"] == {}
    assert rep["ambiguous"][0]["reason"].startswith("several players share this name")


def test_unknown_player_is_reported_not_dropped():
    rep = build_fpl_id_map(FPL, [_u("u1", "Someone Else", "Arsenal")])
    assert rep["unmatched"][0]["understat_id"] == "u1"


def test_overrides_win_over_everything():
    """The escape hatch for names no rule can join — and the only place a human judgement
    enters the map."""
    rep = build_fpl_id_map(FPL, [_u("u1", "Gabriel", "Arsenal")], overrides={"u1": 3})
    assert rep["map"] == {"u1": 3}
    assert rep["matched_by"]["u1"] == "override"
    assert rep["ambiguous"] == []


def test_falls_back_to_web_name_when_no_full_name():
    rep = build_fpl_id_map(
        [{"element_id": 7, "web_name": "Saka", "team": "Arsenal"}],
        [_u("u1", "Saka", "Arsenal")],
    )
    assert rep["map"] == {"u1": 7}


def test_coverage_reports_the_share_joined():
    players = [_u("u1", "Bukayo Saka", "Arsenal"), _u("u2", "Nobody Here", "Arsenal")]
    rep = build_fpl_id_map(FPL, players)
    assert coverage(rep, players) == 0.5
    assert coverage(rep, []) == 0.0


# --- shot zones ---------------------------------------------------------------------------- #
def test_zones_split_the_pitch_into_three_channels():
    assert shot_zone(0.1) == "left"
    assert shot_zone(0.5) == "central"
    assert shot_zone(0.9) == "right"


def test_zone_boundaries_are_central():
    """Exactly on a third is central — a shot from the edge of the channel is not a flank
    attack, and this keeps the three shares summing to 1 with no double counting."""
    assert shot_zone(1 / 3) == "central"
    assert shot_zone(2 / 3) == "central"


def test_shares_sum_to_one_and_track_the_counts():
    shots = [{"Y": 0.1}] * 5 + [{"Y": 0.5}] * 3 + [{"Y": 0.9}] * 2
    z = zone_shares(shots)
    assert z["shots"] == 10
    assert z["counts"] == {"left": 5, "central": 3, "right": 2}
    assert sum(z["shares"].values()) == 1.0
    assert z["shares"]["left"] == 0.5


def test_lowercase_y_key_is_accepted():
    assert zone_shares([{"y": 0.1}])["counts"]["left"] == 1


def test_shots_without_coordinates_are_skipped_not_counted():
    z = zone_shares([{"Y": 0.1}, {"Y": None}, {}])
    assert z["shots"] == 1


def test_a_small_sample_is_flagged_unreliable():
    """A 100%-left share off three shots is noise. The flag is what stops the UI printing it
    as a tendency."""
    assert zone_shares([{"Y": 0.1}] * 3)["reliable"] is False
    assert zone_shares([{"Y": 0.1}] * MIN_SHOTS_FOR_SHARE)["reliable"] is True


def test_empty_input_yields_zero_shares_not_a_crash():
    z = zone_shares([])
    assert z["shots"] == 0 and z["shares"] == {"left": 0.0, "central": 0.0, "right": 0.0}
    assert z["reliable"] is False
