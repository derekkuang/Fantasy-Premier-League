"""Scoreline-matrix math: the one object the whole system derives from."""

import math

from fpledge.models import match_engine as me


def test_matrix_normalised():
    m = me.scoreline_matrix(1.6, 1.1, rho=-0.03)
    total = sum(sum(row) for row in m)
    assert math.isclose(total, 1.0, abs_tol=1e-9)


def test_1x2_probabilities_sum_to_one():
    p = me.derive(1.6, 1.1)
    assert math.isclose(p.home_win + p.draw + p.away_win, 1.0, abs_tol=1e-9)


def test_clean_sheet_equals_matrix_column():
    # Home clean sheet = P(away scores 0) = sum of column 0.
    p = me.derive(1.4, 1.2)
    col0 = sum(p.matrix[i][0] for i in range(len(p.matrix)))
    assert math.isclose(p.clean_sheet_home, col0, abs_tol=1e-12)


def test_stronger_home_team_more_likely_to_win():
    strong = me.derive(2.2, 0.7)
    even = me.derive(1.3, 1.3)
    assert strong.home_win > even.home_win
    assert strong.clean_sheet_home > even.clean_sheet_home


def test_over_under_complementary():
    p = me.derive(1.5, 1.5)
    under_2_5 = sum(
        p.matrix[i][j]
        for i in range(len(p.matrix))
        for j in range(len(p.matrix))
        if i + j <= 2
    )
    assert math.isclose(p.over_2_5 + under_2_5, 1.0, abs_tol=1e-9)
