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


def test_from_recent_reflects_current_form():
    mm = MinutesModel()
    nailed = mm.from_recent([90, 90, 90, 90])
    assert nailed.p_60 > 0.95 and nailed.x_minutes > 85
    # recency: recently-nailed should score far higher than recently-dropped
    dropped = mm.from_recent([90, 90, 0, 0])
    returned = mm.from_recent([0, 0, 90, 90])
    assert returned.p_60 > dropped.p_60
    assert mm.from_recent([]).p_play == 0.0


def test_from_recent_availability_scaling():
    mm = MinutesModel()
    full = mm.from_recent([90, 90, 90, 90])
    doubt = mm.from_recent([90, 90, 90, 90], chance_of_playing=25)
    assert abs(doubt.p_60 - 0.25 * full.p_60) < 1e-9


def test_apply_availability():
    mm = MinutesModel()
    base = mm.from_season(3000, 34)
    assert mm.apply_availability(base, status="a").p_60 == base.p_60           # available: unchanged
    inj = mm.apply_availability(base, status="i")
    assert inj.p_play == 0.0 and inj.p_60 == 0.0 and inj.x_minutes == 0.0       # injured: zeroed
    doubt = mm.apply_availability(base, chance_of_playing=50)
    assert abs(doubt.p_60 - 0.5 * base.p_60) < 1e-9                             # doubtful: scaled
