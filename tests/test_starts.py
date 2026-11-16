"""The start-probability minutes model (docs/MODEL_FIXES.md E6)."""

import json
import random

import pytest

from fpledge.eval import start_model as sm
from fpledge.models import starts


def test_features_read_the_history():
    hist = [(90, 1), (90, 1), (0, 0), (25, 0), (90, 1)]
    f = dict(zip(starts.FEATURES, starts.features(hist, "DEF"), strict=True))
    assert f["started last"] == 1.0 and f["starts of last 3"] == pytest.approx(1 / 3)
    assert f["starts of last 5"] == pytest.approx(3 / 5) and f["appearances of last 5"] == pytest.approx(4 / 5)
    assert f["since last start"] == 0.0 and f["since last appearance"] == 0.0
    assert f["minutes when starting"] == pytest.approx(1.0) and f["DEF"] == 1.0 and f["MID"] == 0.0
    out = dict(zip(starts.FEATURES, starts.features([(90, 1), (0, 0), (0, 0)], "GK"), strict=True))
    assert out["since last appearance"] == pytest.approx(0.2) and out["DEF"] == out["FWD"] == 0.0


def test_double_gameweek_counts_once():
    assert starts.clip_gw(180, 2) == (90, 1)


def _model():
    zero = [0.0] * len(starts.FEATURES)
    return starts.StartModel(start=(0.0, zero), sub=(0.0, zero), sixty=(2.0, zero),
                             minutes=(80.0, zero), sub_minutes=20.0, trained_on=["t"], c=1.0)


def test_predict_combines_the_parts():
    mp = _model().predict([(90, 1)], "MID")
    p60 = 1 / (1 + pytest.importorskip("math").exp(-2.0))
    assert mp.p_play == pytest.approx(0.5 + 0.5 * 0.5)
    assert mp.p_60 == pytest.approx(0.5 * p60)
    assert mp.x_minutes == pytest.approx(0.5 * 80 + 0.5 * 0.5 * 20)
    assert _model().predict([], "MID").p_play == 0.0


def test_json_round_trip_and_feature_guard(tmp_path):
    m = _model()
    path = tmp_path / "m.json"
    path.write_text(json.dumps(m.to_json()))
    assert starts.load(path).predict([(90, 1)], "DEF") == m.predict([(90, 1)], "DEF")
    bad = m.to_json() | {"features": ["something else"]}
    with pytest.raises(ValueError):
        starts.StartModel.from_json(bad)


def test_fit_learns_that_starters_start():
    rng = random.Random(0)
    hist = {}
    for el in range(60):
        nailed = el < 30
        games = []
        for _ in range(12):
            u = rng.random()
            if nailed or u < 0.2:
                games.append((rng.choice((90, 90, 55)), 1))      # a start, sometimes off early
            else:
                games.append((rng.choice((0, 20)), 0))          # benched, sometimes on
        hist[el] = ("MID", games)
    m = starts.fit(starts.training_rows(hist), ["synthetic"], c=1.0)
    assert m.predict([(90, 1)] * 6, "MID").p_play > m.predict([(0, 0)] * 6, "MID").p_play


def test_expected_rows_is_the_union():
    assert sm.expected_rows({(1, 1): 0.6, (1, 2): 0.2}, {(1, 2): 0.7, (1, 3): 0.1}) == {(1, 1), (1, 2)}


def test_shipped_model_loads():
    m = starts.load()
    assert m.trained_on == ["2023-24", "2024-25", "2025-26"]
    nailed = m.predict([(90, 1)] * 8, "DEF")
    benched = m.predict([(0, 0)] * 8, "DEF")
    # a player who started all eight is likely but not certain to play (§44: 0.90, not 1.00)
    assert 0.8 < nailed.p_play < 0.97 and 70 < nailed.x_minutes <= 90
    assert benched.p_play < 0.3


class _Engine:
    def knows(self, _team):
        return True

    def predict(self, _h, _a):
        return type("P", (), {"lam_home": 1.4, "lam_away": 1.1,
                              "clean_sheet_home": 0.33, "clean_sheet_away": 0.25})()


def _xmin(recent_minutes=None, starts_by_gw=None):
    from fpledge.models.xp_table import compute_xp_records

    player = {"code": 1, "element_id": 11, "team_id": 1, "position": "MID", "web_name": "P",
              "minutes": 3000, "starts": 34, "xg": 8.0, "xa": 6.0, "dc": 40, "bonus": 12,
              "ownership": 20.0}
    recs, _, _ = compute_xp_records([player], {1: "A", 2: "B"}, [(1, 2)], _Engine(),
                                    {"A": "A", "B": "B"}, {1: 7.5}, recent_minutes=recent_minutes,
                                    starts_by_gw=starts_by_gw)
    return recs[0]["x_minutes"]


def test_production_takes_the_start_model_after_the_switch():
    from fpledge.models.minutes import MinutesModel

    mins, sts = [90] * 6, [1] * 6
    model = starts.load().predict(list(zip(mins, sts, strict=True)), "MID").x_minutes
    assert _xmin({1: mins}, {1: sts}) == pytest.approx(model)
    assert _xmin({1: mins}) == pytest.approx(MinutesModel().from_recent(mins).x_minutes)  # no starts: old path
    assert _xmin({1: [0] * 6}, {1: [0] * 6}) == _xmin()          # the all-zero guard still holds
    assert _xmin({1: [90] * 3}, {1: [1] * 3}) == _xmin()         # so does the four-gameweek switch
