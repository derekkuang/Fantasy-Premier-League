"""The from-scratch Dixon-Coles fit must recover team strength from results.

Skipped automatically when numpy/scipy aren't installed, so the stdlib-only core
test suite still runs with just pytest.
"""

import pytest

pytest.importorskip("numpy")
pytest.importorskip("scipy")

from fpledge.models.dixon_coles import DixonColesModel  # noqa: E402


def _synthetic_matches():
    # A is strong, C is weak, B is in between. Same scripted round played repeatedly.
    round_ = [
        ("A", "B", 2, 1), ("A", "C", 3, 0), ("B", "C", 2, 1),
        ("B", "A", 1, 1), ("C", "A", 0, 2), ("C", "B", 1, 1),
    ]
    matches, ord_ = [], 739000
    for _ in range(15):
        for home, away, hg, ag in round_:
            matches.append(
                {"home": home, "away": away, "home_goals": hg, "away_goals": ag, "date_ord": ord_}
            )
            ord_ += 3
    return matches


def test_fit_converges_and_recovers_strength():
    model = DixonColesModel(half_life_days=1e6).fit(_synthetic_matches())  # ~no decay
    assert model.converged
    assert model.knows("A") and model.knows("C")

    lam_h, lam_a = model.expected_goals("A", "C")
    assert lam_h > lam_a  # strong home team out-scores weak away team

    a_vs_c = model.predict("A", "C")
    c_vs_a = model.predict("C", "A")
    assert a_vs_c.home_win > a_vs_c.away_win          # A beats C
    assert a_vs_c.home_win > c_vs_a.home_win          # A at home vs C >> C at home vs A


def test_probabilities_are_normalised():
    model = DixonColesModel().fit(_synthetic_matches())
    p = model.predict("A", "B")
    assert abs(p.home_win + p.draw + p.away_win - 1.0) < 1e-9


def test_unknown_team_uses_promoted_prior():
    model = DixonColesModel(half_life_days=1e6).fit(_synthetic_matches())
    assert model.knows("A") and not model.knows("ZZ_promoted")
    # a known strong team out-scores the promoted-prior team against the same opponent
    lam_strong, _ = model.expected_goals("A", "B")
    lam_promoted, _ = model.expected_goals("ZZ_promoted", "B")
    assert lam_promoted < lam_strong
    # predict() no longer raises on an unknown team, and stays a valid distribution
    p = model.predict("ZZ_promoted", "B")
    assert abs(p.home_win + p.draw + p.away_win - 1.0) < 1e-9
