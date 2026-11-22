"""E5's decision helpers: the save-term gap, its interval, and the rule."""

import pytest

from fpledge.eval import save_rounding as sr

GWS = tuple(range(1, 21))


def _rows(projected, awarded, gws=GWS, per_gw=20, p_play=0.9):
    return [{"season": "s", "gw": g, "p_play": p_play, "projected": projected, "awarded": a}
            for g in gws for i in range(per_gw) for a in [awarded[i % len(awarded)]]]


def test_term_sums_keep_only_expected_starters():
    rows = _rows(0.6, [1]) + _rows(5.0, [0], p_play=0.2)
    sums = sr.term_sums(rows)
    assert all(v["n"] == 20 for v in sums.values())
    assert sr.term_gap(sums)["gap"] == pytest.approx(0.4)


def test_gap_interval_covers_a_calibrated_term_and_flags_an_overpaying_one():
    awarded = [0, 0, 1, 0, 1, 2, 0, 1, 0, 1]   # mean 0.6
    good = sr.term_gap(sr.term_sums(_rows(0.6, awarded)))
    bad = sr.term_gap(sr.term_sums(_rows(0.9, awarded)))
    assert good["gap"] == pytest.approx(0.0) and sr.reaches(good["ci"])
    assert bad["gap"] == pytest.approx(-0.3) and not sr.reaches(bad["ci"])
    assert bad["ci"][0] <= bad["gap"] <= bad["ci"][1]


def test_reaches_is_overlap_with_the_tolerance_band():
    assert sr.reaches([-0.2, -0.04])
    assert sr.reaches([0.04, 0.3])
    assert not sr.reaches([-0.4, -0.06])
    assert not sr.reaches([0.06, 0.1])


def _g(gap, lo, hi):
    return {"gap": gap, "ci": [lo, hi]}


def test_verdict_three_ways():
    assert sr.verdict({"floor": _g(-0.01, -0.1, 0.08), "production": _g(-0.3, -0.4, -0.2)}) == "SHIP"
    assert sr.verdict({"floor": _g(0.3, 0.2, 0.4), "production": _g(0.0, -0.1, 0.1)}) == "DO NOT SHIP"
    assert sr.verdict({"floor": _g(0.0, -0.1, 0.1), "production": _g(-0.1, -0.2, 0.0)}) == "INCONCLUSIVE"
    assert sr.verdict({"floor": _g(-0.2, -0.3, -0.1), "production": _g(-0.5, -0.6, -0.4)}) == "INCONCLUSIVE"


def test_development_needs_every_season_and_both_pooled_rules():
    seasons = {s: {"floor": _g(-0.01, -0.05, 0.03), "production": _g(-0.3, -0.35, -0.25)}
               for s in ("a", "b", "c")}
    mse_ok, rho_ok = {"ci": [-0.1, -0.05]}, {"ci": [-0.0015, 0.001]}
    assert sr.development(seasons, mse_ok, rho_ok)["proceed"]
    assert not sr.development(seasons, mse_ok, {"ci": [-0.003, 0.001]})["proceed"]
    assert not sr.development(seasons, {"ci": [-0.1, 0.01]}, rho_ok)["proceed"]
    one_off = {**seasons, "c": {"floor": _g(-0.2, -0.3, -0.1), "production": _g(-0.3, -0.35, -0.25)}}
    assert not sr.development(one_off, mse_ok, rho_ok)["proceed"]
    assert not sr.development({}, mse_ok, rho_ok)["proceed"]
