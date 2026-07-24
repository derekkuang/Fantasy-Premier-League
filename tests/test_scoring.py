"""FPL 2025/26 scoring, with focus on the new Defensive Contribution point."""

from fpledge import config
from fpledge.scoring import StatLine, defensive_contribution_points, total_points


def test_defender_dc_threshold():
    # DEF needs 10+ CBIT for the +2.
    assert defensive_contribution_points("DEF", cbit=9, recoveries=0) == 0
    assert defensive_contribution_points("DEF", cbit=10, recoveries=0) == config.DC_POINTS
    # Recoveries do NOT count for defenders.
    assert defensive_contribution_points("DEF", cbit=9, recoveries=50) == 0


def test_mid_fwd_dc_threshold_uses_recoveries():
    # MID/FWD need 12+ CBIRT (recoveries included).
    assert defensive_contribution_points("MID", cbit=8, recoveries=3) == 0   # 11
    assert defensive_contribution_points("MID", cbit=8, recoveries=4) == config.DC_POINTS  # 12
    assert defensive_contribution_points("FWD", cbit=12, recoveries=0) == config.DC_POINTS


def test_gk_has_no_dc():
    assert defensive_contribution_points("GK", cbit=50, recoveries=50) == 0


def test_defender_clean_sheet_and_dc_stack():
    # 90 mins, clean sheet (4), 1 goal (6), 10 CBIT (+2) = 2 appearance + 6 + 4 + 2
    s = StatLine(position="DEF", minutes=90, goals=1, goals_conceded=0, cbit=10)
    assert total_points(s) == config.APPEARANCE_60_POINTS + 6 + 4 + 2


def test_clean_sheet_requires_60_minutes():
    s = StatLine(position="DEF", minutes=45, goals_conceded=0)
    assert s.clean_sheet is False
    # 1 appearance point only (sub), no clean sheet.
    assert total_points(s) == config.APPEARANCE_SUB_POINTS


def test_keeper_saves_and_concede():
    # GK 90 mins, 6 saves (+2), 2 conceded (-1), no clean sheet.
    s = StatLine(position="GK", minutes=90, saves=6, goals_conceded=2)
    expected = config.APPEARANCE_60_POINTS + (6 // config.SAVES_PER_POINT) - 1
    assert total_points(s) == expected
