"""Per-match previews: the serialised scoreline distribution.

These assert the *distribution* properties (mass, consistency between derived markets) rather
than specific numbers — the numbers come from `derive()`, which test_match_engine already
covers. What's new here is the reshaping, and the ways reshaping can silently lie: a
top-N scoreline list that claims more coverage than it has, or a clean-sheet field attributed
to the wrong side.
"""

from __future__ import annotations

import pytest

from fpledge.matches import TOP_SCORELINES, match_id, match_previews
from fpledge.models.match_engine import derive


class _FakeEngine:
    def knows(self, name):
        return True

    def predict(self, home, away):
        return derive(1.8, 1.1)


FIXTURES = [
    {"gw": 1, "home_id": 1, "away_id": 2},
    {"gw": 2, "home_id": 2, "away_id": 1},
    {"gw": 9, "home_id": 1, "away_id": 2},   # outside an 8-gw horizon from gw 1
]
TEAMS = {1: "Alpha", 2: "Beta"}
TMAP = {"Alpha": "Alpha", "Beta": "Beta"}


def _previews(**kw):
    return match_previews(_FakeEngine(), FIXTURES, TEAMS, TMAP, start_gw=1, **kw)


def test_horizon_window_is_respected():
    got = _previews(horizon=8)
    assert [m["gw"] for m in got] == [1, 2]      # gw 9 is outside the window


def test_match_id_is_stable_and_unique_per_fixture():
    got = _previews()
    assert {m["match_id"] for m in got} == {match_id(1, 1, 2), match_id(2, 2, 1)}
    assert match_id(1, 1, 2) != match_id(1, 2, 1)   # reversed fixture is a different match


def test_result_probabilities_form_a_distribution():
    r = _previews()[0]["result"]
    assert sum(r.values()) == pytest.approx(1.0, abs=1e-3)
    assert all(0.0 <= v <= 1.0 for v in r.values())


def test_over_and_under_are_complements():
    m = _previews()[0]
    assert m["over_2_5"] + m["under_2_5"] == pytest.approx(1.0, abs=1e-3)


def test_home_favoured_when_home_lambda_is_higher():
    """Sanity on orientation — a mis-wired home/away swap would pass every sum check above."""
    m = _previews()[0]           # lam_home 1.8 vs lam_away 1.1
    assert m["result"]["home_win"] > m["result"]["away_win"]
    assert m["lam_home"] > m["lam_away"]


def test_clean_sheet_is_attributed_to_the_side_that_keeps_it():
    """`clean_sheet.home` is P(away fails to score). The stronger attack concedes less, so the
    home side — outscoring here — must hold the higher clean-sheet probability."""
    m = _previews()[0]
    assert m["clean_sheet"]["home"] > m["clean_sheet"]["away"]


def test_scorelines_are_ranked_and_coverage_is_honest():
    m = _previews()[0]
    ps = [s["p"] for s in m["scorelines"]]
    assert len(m["scorelines"]) == TOP_SCORELINES
    assert ps == sorted(ps, reverse=True)
    # the stated coverage must match what the listed scorelines actually sum to, and must not
    # claim the whole distribution — the tail is real
    assert m["scorelines_p"] == pytest.approx(sum(ps), abs=1e-3)
    assert m["scorelines_p"] < 1.0


def test_most_likely_score_is_the_top_scoreline():
    m = _previews()[0]
    top = m["scorelines"][0]
    assert m["most_likely_score"] == [top["home"], top["away"]]


def test_market_lambdas_override_the_engine_and_tag_the_source():
    got = match_previews(
        _FakeEngine(), FIXTURES, TEAMS, TMAP, start_gw=1, horizon=8,
        market_lambdas={(1, 2): (0.9, 2.4)},
    )
    priced = next(m for m in got if m["gw"] == 1)
    engine_only = next(m for m in got if m["gw"] == 2)
    assert priced["source"] == "market"
    assert (priced["lam_home"], priced["lam_away"]) == (0.9, 2.4)
    assert priced["result"]["away_win"] > priced["result"]["home_win"]  # market flips the tie
    assert engine_only["source"] == "model"


def test_each_sides_fdr_reads_from_the_right_lambda():
    """A side's attack rating comes from the goals it scores, its defence rating from the goals
    it concedes — i.e. from the OPPONENT's lambda. Transposing those would hand a team its
    opponent's difficulty, and every distribution check above would still pass."""
    lopsided = match_previews(
        _FakeEngine(), [FIXTURES[0]], TEAMS, TMAP, start_gw=1,
        market_lambdas={(1, 2): (3.0, 0.4)},   # home scores freely, away barely
    )[0]
    home, away = lopsided["fdr"]["home"], lopsided["fdr"]["away"]
    assert home["attack"] < away["attack"]      # home has the easier job scoring
    assert home["defence"] < away["defence"]    # ...and the easier clean sheet
