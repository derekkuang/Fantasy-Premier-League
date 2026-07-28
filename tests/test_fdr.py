"""True FDR: expected goals mapped to a 1 (easy) .. 5 (hard) scale, correct direction."""

from fpledge.fdr import attack_fdr, defence_fdr


def test_attack_fdr_direction_and_bounds():
    assert attack_fdr(2.5) < attack_fdr(1.0)     # more expected goals-for = easier attack
    assert 1 <= attack_fdr(1.5) <= 5


def test_defence_fdr_direction_and_bounds():
    assert defence_fdr(0.7) < defence_fdr(2.0)   # fewer expected goals-against = easier CS
    assert 1 <= defence_fdr(1.2) <= 5
