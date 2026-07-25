"""Goal/assist shares: attribution must sum to 1 within a team and be xG-proportional."""

from fpledge.models.shares import match_shares, team_minutes, team_shares


def test_shares_sum_to_one_and_proportional():
    players = [
        {"code": 1, "team_id": 10, "xg": 8.0, "xa": 4.0},
        {"code": 2, "team_id": 10, "xg": 2.0, "xa": 0.0},
    ]
    s = team_shares(players)
    assert abs(s[1]["goal_share"] - 0.8) < 1e-9
    assert abs(s[2]["goal_share"] - 0.2) < 1e-9
    assert abs(s[1]["goal_share"] + s[2]["goal_share"] - 1.0) < 1e-9
    assert s[1]["assist_share"] == 1.0  # only player with xA on the team


def test_zero_team_xg_gives_zero_share():
    s = team_shares([{"code": 1, "team_id": 5, "xg": 0.0, "xa": 0.0}])
    assert s[1]["goal_share"] == 0.0
    assert s[1]["assist_share"] == 0.0


def test_teams_are_independent():
    players = [
        {"code": 1, "team_id": 1, "xg": 5.0, "xa": 0.0},
        {"code": 2, "team_id": 2, "xg": 3.0, "xa": 0.0},
    ]
    s = team_shares(players)
    assert s[1]["goal_share"] == 1.0  # sole scorer on team 1
    assert s[2]["goal_share"] == 1.0  # sole scorer on team 2


def test_match_shares_is_minutes_aware():
    # Identical per-90 rate, but player 1 plays a full match and player 2 only half.
    players = [
        {"code": 1, "team_id": 10, "minutes": 3000, "xg": 15.0, "xa": 0.0},
        {"code": 2, "team_id": 10, "minutes": 3000, "xg": 15.0, "xa": 0.0},
    ]
    s = match_shares(players, {1: 90.0, 2: 45.0})
    assert abs(s[1]["goal_share"] + s[2]["goal_share"] - 1.0) < 1e-9
    assert abs(s[1]["goal_share"] - 2 / 3) < 1e-9  # 90:45 minutes -> 2:1 split


def test_match_shares_excludes_tiny_samples():
    players = [
        {"code": 1, "team_id": 5, "minutes": 3000, "xg": 10.0, "xa": 0.0},
        {"code": 2, "team_id": 5, "minutes": 100, "xg": 5.0, "xa": 0.0},  # <270 min -> ignored
    ]
    s = match_shares(players, {1: 90.0, 2: 90.0})
    assert s[1]["goal_share"] == 1.0
    assert s[2]["goal_share"] == 0.0


def test_team_minutes_coverage():
    players = [
        {"code": 1, "team_id": 1, "minutes": 1000},
        {"code": 2, "team_id": 1, "minutes": 500},
        {"code": 3, "team_id": 2, "minutes": 800},
    ]
    tm = team_minutes(players)
    assert tm[1] == 1500
    assert tm[2] == 800
