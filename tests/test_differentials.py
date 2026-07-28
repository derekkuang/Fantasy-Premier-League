"""Differential finder: high-xP, low-owned, above an xP floor, excluding low-data teams."""

from fpledge.differentials import find_differentials


def _recs():
    return [
        {"web_name": "A", "position": "MID", "xp": 6.0, "ownership": 5.0, "diff_value": 5.7, "low_cov": False},
        {"web_name": "B", "position": "MID", "xp": 6.5, "ownership": 60.0, "diff_value": 2.6, "low_cov": False},
        {"web_name": "C", "position": "FWD", "xp": 3.0, "ownership": 2.0, "diff_value": 2.9, "low_cov": False},
        {"web_name": "D", "position": "DEF", "xp": 5.0, "ownership": 8.0, "diff_value": 4.6, "low_cov": True},
    ]


def test_finds_high_xp_low_owned():
    names = [r["web_name"] for r in find_differentials(_recs(), max_ownership=15, min_xp=3.5)]
    assert "A" in names       # low-owned, high xP
    assert "B" not in names    # too owned
    assert "C" not in names    # below the xP floor
    assert "D" not in names    # low-data team excluded


def test_position_filter_and_sort():
    recs = _recs() + [
        {"web_name": "E", "position": "MID", "xp": 7.0, "ownership": 3.0, "diff_value": 6.8, "low_cov": False},
    ]
    out = find_differentials(recs, max_ownership=15, min_xp=3.5, position="MID")
    assert all(r["position"] == "MID" for r in out)
    assert out[0]["web_name"] == "E"  # ranked by differential value
