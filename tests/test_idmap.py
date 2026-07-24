"""FPL<->external id mapping — the join that silently corrupts everything if wrong."""

from fpledge.ingest import idmap


def test_normalize_handles_accents_and_special_letters():
    assert idmap.normalize_name("Son Heung-min") == "son heung min"
    assert idmap.normalize_name("Martin Ødegaard") == "martin odegaard"   # ø has no NFKD
    assert idmap.normalize_name("N'Golo Kanté") == "n golo kante"
    assert idmap.normalize_name("João Félix") == "joao felix"


def test_token_overlap_matches_short_alias():
    # "Son" must match "Son Heung-min" even though the raw sequence ratio is low.
    assert idmap.name_similarity("Son", "Son Heung-min") >= 0.6


FPL = [
    {"element_id": 1, "name": "Haaland", "team": "Man City"},
    {"element_id": 2, "name": "Son Heung-min", "team": "Spurs"},
    {"element_id": 3, "name": "Ødegaard", "team": "Arsenal"},
]
EXT = [
    {"ext_id": "u1", "name": "Erling Haaland", "team": "Man City"},
    {"ext_id": "u2", "name": "Son", "team": "Spurs"},
    {"ext_id": "u3", "name": "Martin Odegaard", "team": "Arsenal"},
    {"ext_id": "u99", "name": "Totally Unknown", "team": "Arsenal"},
]


def test_match_players_maps_and_flags_unmatched():
    mapping, unmatched = idmap.match_players(FPL, EXT)
    assert mapping["u1"] == 1
    assert mapping["u2"] == 2
    assert mapping["u3"] == 3
    assert "u99" in unmatched          # below threshold -> honest gap, not forced
    assert "u99" not in mapping


def test_overrides_bypass_fuzzy_matching():
    mapping, _ = idmap.match_players(FPL, EXT, overrides={"u99": 3})
    assert mapping["u99"] == 3
