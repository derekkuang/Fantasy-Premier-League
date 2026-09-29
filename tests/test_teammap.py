"""FPL <-> Football-Data team-name mapping — the engine->FPL bridge."""

from fpledge.models.teammap import build_team_map


def test_maps_exact_fuzzy_and_overrides_flags_unknown():
    fpl = ["Man City", "Man Utd", "Spurs", "Coventry"]
    fd = ["Man City", "Man United", "Tottenham", "Arsenal"]
    m = build_team_map(fpl, fd)
    assert m["Man City"] == "Man City"     # exact
    assert m["Man Utd"] == "Man United"    # override (fuzzy would be shaky)
    assert m["Spurs"] == "Tottenham"       # override (no shared tokens)
    assert m["Coventry"] is None           # promoted, absent from engine history


def test_wolves_and_forest_match_by_name():
    fpl = ["Wolves", "Nott'm Forest", "Newcastle"]
    fd = ["Wolves", "Nott'm Forest", "Newcastle", "Everton"]
    m = build_team_map(fpl, fd)
    assert m["Wolves"] == "Wolves"
    assert m["Nott'm Forest"] == "Nott'm Forest"
    assert m["Newcastle"] == "Newcastle"


# --- odds-feed names: a different question from the engine's team map -------------------- #
FPL_2026 = [
    "Arsenal", "Aston Villa", "Bournemouth", "Brentford", "Brighton", "Chelsea",
    "Coventry City", "Crystal Palace", "Everton", "Fulham", "Hull City", "Ipswich Town",
    "Leeds", "Liverpool", "Man City", "Man Utd", "Newcastle", "Nott'm Forest", "Spurs",
    "Sunderland",
]


def test_promoted_clubs_map_from_an_odds_feed():
    """The bug this function exists for. `build_team_map` builds its candidates from the
    SEASONS THE ENGINE WAS FITTED ON, where a newly promoted club has never appeared — so
    Coventry and Hull mapped to None and their betting lines were dropped, even though the
    matcher scores both at 1.000 against the FPL names. The engine is entitled to say "no
    history"; the odds path is not, because a bookmaker prices them regardless.
    """
    from fpledge.models.teammap import build_odds_team_map

    got = build_odds_team_map(FPL_2026, ["Arsenal", "Coventry", "Hull", "Man United"])
    assert got["Coventry"] == "Coventry City"
    assert got["Hull"] == "Hull City"
    assert got["Man United"] == "Man Utd"
    assert got["Arsenal"] == "Arsenal"


def test_a_partial_slate_cannot_hand_one_club_another_s_odds():
    """The hazard stable matching removes. "Man Utd" scores 0.667 against "Man City", above the
    0.6 threshold, so on a week where City play and United do not, plain best-match assigns
    City's price to United — a wrong number that looks entirely normal. City must claim itself
    first and United must go unpriced."""
    from fpledge.models.teammap import build_odds_team_map

    got = build_odds_team_map(FPL_2026, ["Man City", "Bournemouth"])
    assert got["Man City"] == "Man City"
    assert "Man Utd" not in got.values()
    assert set(got) == {"Man City", "Bournemouth"}


def test_the_odds_api_full_names_resolve():
    """The Odds API writes clubs out in full. Measured against the FPL names the matcher puts
    "Manchester United" at 0.583 and "Tottenham Hotspur" at 0.467 — both below threshold — so
    they ride on the override table rather than on luck."""
    from fpledge.models.teammap import build_odds_team_map

    got = build_odds_team_map(FPL_2026, [
        "Manchester United", "Manchester City", "Tottenham Hotspur", "Nottingham Forest",
        "AFC Bournemouth", "Brighton and Hove Albion", "Leeds United", "Newcastle United",
    ])
    assert got["Manchester United"] == "Man Utd"
    assert got["Manchester City"] == "Man City"
    assert got["Tottenham Hotspur"] == "Spurs"
    assert got["Nottingham Forest"] == "Nott'm Forest"
    assert got["AFC Bournemouth"] == "Bournemouth"
    assert got["Brighton and Hove Albion"] == "Brighton"
    assert len(set(got.values())) == len(got)          # nothing claimed twice


def test_an_unknown_club_maps_to_nothing_rather_than_the_nearest_thing():
    """A feed naming a club we do not carry must drop out, not land on whoever scores best."""
    from fpledge.models.teammap import build_odds_team_map

    got = build_odds_team_map(FPL_2026, ["Real Madrid"])
    assert got == {}
