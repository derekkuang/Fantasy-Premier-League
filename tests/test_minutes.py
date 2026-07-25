"""Minutes model: the preseason from-season proxy behaves sensibly."""

from fpledge.models.minutes import MinutesModel


def test_from_season_nailed_starter():
    mp = MinutesModel().from_season(minutes=3040, starts=34)  # ~80 mins, 34/38 starts
    assert mp.p_60 > 0.85
    assert mp.p_play >= mp.p_60
    assert 70 < mp.x_minutes < 90


def test_from_season_pure_sub():
    mp = MinutesModel().from_season(minutes=380, starts=0)
    assert mp.p_60 == 0.0
    assert 0.0 < mp.p_play <= 0.2
    assert mp.x_minutes == 10.0


def test_from_season_no_minutes():
    mp = MinutesModel().from_season(minutes=0, starts=0)
    assert mp.p_play == 0.0 and mp.p_60 == 0.0 and mp.x_minutes == 0.0
