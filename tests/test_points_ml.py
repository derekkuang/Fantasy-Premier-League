"""LightGBM points model: feature extraction must be point-in-time; training must run."""

import copy

import pytest

pytest.importorskip("numpy")
pytest.importorskip("scipy")

from fpledge.models.points_ml import FEATURES, extract_features


def _synthetic():
    teams = {"A": 1, "B": 2}
    kicks = ["2025-08-15", "2025-08-22", "2025-08-29", "2025-09-05", "2025-09-12", "2025-09-19"]
    fixtures = [
        {"gw": g, "home": ("1" if g % 2 else "2"), "away": ("2" if g % 2 else "1"),
         "home_goals": 2, "away_goals": 1, "kickoff": kicks[g - 1] + "T15:00:00Z"}
        for g in range(1, 7)
    ]
    plan = [(101, "A", "MID"), (102, "A", "DEF"), (103, "A", "FWD"), (104, "A", "GK"),
            (201, "B", "MID"), (202, "B", "DEF"), (203, "B", "FWD"), (204, "B", "GK")]
    rows = []
    for g in range(1, 7):
        for el, team, pos in plan:
            tid = teams[team]
            rows.append(
                {"element": el, "name": f"p{el}", "position": pos, "team": team, "gw": g,
                 "opponent_team": (2 if tid == 1 else 1), "was_home": ((g % 2 == 1) == (tid == 1)),
                 "minutes": 90, "starts": 1, "xg": 0.2, "xa": 0.1, "dc": 6, "bonus": 1,
                 "total_points": 4, "fpl_xp": 3.5}
            )
    return rows, fixtures, teams


def test_features_present_and_point_in_time():
    rows, fixtures, teams = _synthetic()
    base = extract_features(rows, fixtures, teams, burn_in=2, min_rate_minutes=90)
    assert base and all(f in base[0] for f in FEATURES)

    corrupt = copy.deepcopy(rows)
    for r in corrupt:                      # blow up GW6 inputs AND its realized points
        if r["gw"] == 6:
            r["xg"], r["dc"], r["total_points"] = 99.0, 99, 99
    after = extract_features(corrupt, fixtures, teams, burn_in=2, min_rate_minutes=90)

    def feats(rowset):
        return {(r["gw"], r["element"]): tuple(r[f] for f in FEATURES)
                for r in rowset if r["gw"] < 6}

    assert feats(base) == feats(after)  # future GW cannot change earlier feature rows
    assert feats(base)


def test_walk_forward_lgbm_runs():
    pytest.importorskip("lightgbm")
    from fpledge.models.points_ml import walk_forward_lgbm

    rows, fixtures, teams = _synthetic()
    feats = extract_features(rows, fixtures, teams, burn_in=2, min_rate_minutes=90)
    records = walk_forward_lgbm(feats, min_train=8)
    for rec in records:
        assert len(rec) == 7  # (gw, element, pred, fpl_xp, actual, pos, minutes)
