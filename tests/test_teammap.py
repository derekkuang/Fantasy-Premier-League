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
