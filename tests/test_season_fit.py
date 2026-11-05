"""The frozen-vs-rolling replay: above all, that no forecast sees a result it should not.

A leak here would flatter the rolling fit, which is the change under test, so the point-in-time
tests carry the most weight. The stub reports what it was fitted on through `expected_goals`.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fpledge.eval import season_fit
from fpledge.models.dixon_coles import DixonColesModel


class _Stub:
    def fit(self, matches):
        self.dates = [m["date_ord"] for m in matches]
        self.seasons = {m["season"] for m in matches}
        self.known = {m["home"] for m in matches} | {m["away"] for m in matches}
        return self

    def knows(self, team):
        return team in self.known

    def predict(self, home, away):
        return SimpleNamespace(home_win=0.5, draw=0.3, away_win=0.2)

    def expected_goals(self, home, away):
        return (max(self.dates), len(self.dates))      # (latest result seen, how many)


def _match(season, day, home="A", away="B", hg=1, ag=0, **extra):
    return {"season": season, "date_ord": day, "home": home, "away": away,
            "home_goals": hg, "away_goals": ag, **extra}


def _history():
    """Four prior seasons, then a season of ten weekly matches from day 1000."""
    old = [_match(s, base + i) for s, base in
           (("2019-20", 100), ("2020-21", 300), ("2021-22", 500), ("2022-23", 700))
           for i in range(3)]
    return old + [_match("2023-24", 1000 + 7 * i) for i in range(10)]


def test_no_forecast_sees_a_result_from_inside_its_horizon():
    rows = season_fit.replay_season(_history(), "2023-24", _Stub, horizons=(0, 21, 42))
    for r in rows:
        for h, forecast in r["rolling"].items():
            latest_seen, _n = forecast["lam"]
            assert latest_seen < r["date_ord"] - h


def test_the_frozen_fit_never_sees_the_season_it_predicts():
    rows = season_fit.replay_season(_history(), "2023-24", _Stub, horizons=(0,))
    assert {r["frozen"]["lam"] for r in rows} == {(702, 9)}    # three prior seasons, unchanged


def test_only_the_three_prior_seasons_are_fitted():
    """An older season in the pool must not reach the fit: production fits three."""
    seen = []

    class Recording(_Stub):
        def fit(self, matches):
            seen.append({m["season"] for m in matches})
            return super().fit(matches)

    season_fit.replay_season(_history(), "2023-24", Recording, horizons=(0,))
    assert all("2019-20" not in s for s in seen)
    assert seen[0] == {"2020-21", "2021-22", "2022-23"}


def test_with_no_results_yet_rolling_is_the_frozen_fit():
    """Not merely close. The two must be identical until there is something new to learn from,
    or the comparison would be measuring noise in the optimiser."""
    rows = season_fit.replay_season(_history(), "2023-24", _Stub, horizons=(0, 21))
    assert rows[0]["rolling"][0] == rows[0]["frozen"]
    assert rows[2]["rolling"][21] == rows[2]["frozen"]    # day 1014, cut-off 993: nothing yet
    assert rows[9]["rolling"][21]["lam"][1] == 9 + 6      # day 1063, cut-off 1042: six results


def test_a_separate_baseline_stays_frozen_while_the_candidate_rolls():
    """With other settings the candidate has to be measured against production, not itself."""
    class _Baseline(_Stub):
        def expected_goals(self, home, away):
            return ("baseline", len(self.dates))

    rows = season_fit.replay_season(_history(), "2023-24", _Stub, horizons=(0,),
                                    baseline_factory=_Baseline)
    assert all(r["frozen"]["lam"] == ("baseline", 9) for r in rows)
    assert all(r["rolling"][0]["lam"][0] != "baseline" for r in rows)
    assert rows[0]["rolling"][0]["lam"][1] == 9          # nothing yet, but the candidate's own fit
    assert rows[9]["rolling"][0]["lam"][1] == 9 + 9


def test_a_season_without_three_priors_refuses_to_run():
    with pytest.raises(ValueError, match="prior seasons"):
        season_fit.replay_season(_history(), "2021-22", _Stub)


def test_a_club_missing_from_the_fit_is_scored_not_skipped():
    """`walk_forward` skips these. Production gives them a default rating, and they are where the
    rolling fit should help most, so dropping them would remove the point of the test."""
    pool = _history() + [_match("2023-24", 1100, home="Promoted", away="A")]
    rows = season_fit.replay_season(pool, "2023-24", _Stub, horizons=(0,))
    assert len(rows) == 11
    assert [r["new_club"] for r in rows] == [False] * 10 + [True]


def test_rounds_count_games_played_so_a_postponement_does_not_shift_everyone():
    games = [_match("s", 1, "A", "B"), _match("s", 1, "C", "D"), _match("s", 8, "A", "C"),
             _match("s", 15, "B", "D"), _match("s", 16, "A", "D")]
    assert season_fit.rounds(games) == [1, 1, 2, 2, 3]


@pytest.mark.parametrize(("round_", "stage"), [(1, "1-4"), (4, "1-4"), (5, "5-10"), (19, "11-19"),
                                               (38, "20-38"), (39, "20-38")])
def test_stages(round_, stage):
    assert season_fit.stage_of(round_) == stage


# --- scoring -------------------------------------------------------------------------------- #
def _row(season="s", week=0, y=0, frozen=(0.4, 0.3, 0.3), rolling=(0.5, 0.3, 0.2), market=None):
    return {"season": season, "date_ord": 2 + 7 * week, "round": 1, "y": y, "new_club": False,
            "market_probs": market, "market_lam": None,
            "frozen": {"probs": list(frozen), "lam": (1.0, 1.0)},
            "rolling": {0: {"probs": list(rolling), "lam": (1.0, 1.0)}}}


def test_identical_forecasts_compare_as_exactly_zero():
    res = season_fit.compare([_row(week=i, rolling=(0.4, 0.3, 0.3)) for i in range(5)], 0,
                             "log_loss", n_boot=50)
    assert res["diff"] == 0 and res["ci"] == [0, 0]


def test_a_better_forecast_is_a_negative_diff():
    res = season_fit.compare([_row(week=i) for i in range(5)], 0, "log_loss", n_boot=50)
    assert res["diff"] < 0 and res["ci"][1] < 0


def test_the_market_gap_is_zero_on_the_market_and_ignores_matches_without_odds():
    mkt = (0.5, 0.3, 0.2)
    rows = [_row(market=mkt), _row(week=1)]
    res = season_fit.compare(rows, 0, "market_gap", n_boot=50)
    assert res["n"] == 1
    assert res["rolling"] == pytest.approx(0.0) and res["frozen"] > 0


def test_the_interval_is_reproducible():
    rows = [_row(week=i, y=i % 3) for i in range(20)]
    assert (season_fit.compare(rows, 0, "log_loss", n_boot=200)
            == season_fit.compare(rows, 0, "log_loss", n_boot=200))


# --- the decision rule ---------------------------------------------------------------------- #
def _res(diff, lo, hi):
    return {"n": 100, "frozen": 1.0, "rolling": 1.0 + diff, "diff": diff, "ci": [lo, hi]}


def _summary(gap=(-0.01, -0.02, -0.005), loss=(-0.001, -0.01, 0.01), season_diff=-0.01,
             stage=(-0.001, -0.01, 0.01)):
    block = {
        "market_gap": {"pooled": _res(*gap), "stages": {"1-4": _res(*stage)},
                       "seasons": {"a": _res(season_diff, -1, 1), "b": _res(-0.01, -1, 1)}},
        "log_loss": {"pooled": _res(*loss), "stages": {"1-4": _res(*stage)},
                     "seasons": {"a": _res(-0.01, -1, 1)}},
    }
    return {"horizons": {21: block, 42: block}}


def test_the_rule_ships_only_on_everything_at_once():
    assert season_fit.verdict(_summary())["decision"] == "SHIP"


@pytest.mark.parametrize("over", [
    {"loss": (0.02, 0.01, 0.03)},             # log-loss worse, pooled
    {"gap": (0.02, 0.01, 0.03)},              # market gap worse, pooled
    {"stage": (0.02, 0.01, 0.03)},            # worse in one stage, even if fine overall
])
def test_the_rule_refuses_a_clear_harm(over):
    assert season_fit.verdict(_summary(**over))["decision"] == "DO NOT SHIP"


@pytest.mark.parametrize("over", [
    {"gap": (-0.01, -0.02, 0.001)},           # the interval includes zero
    {"season_diff": 0.001},                   # did not replicate in one season
    {"loss": (0.001, -0.01, 0.01)},           # log-loss worse as a point estimate
])
def test_the_rule_leaves_production_alone_without_evidence(over):
    assert season_fit.verdict(_summary(**over))["decision"] == "INCONCLUSIVE"


# --- with the real engine ------------------------------------------------------------------- #
def test_the_rolling_fit_actually_learns_from_this_season():
    """Against the real engine: a club transformed this season should be rated above its past."""
    clubs = ["A", "B", "C", "D"]

    def season(label, base, a_goals):
        games, day = [], base
        for _ in range(4):
            for home in clubs:
                for away in clubs:
                    if home != away:
                        gf, ga = (a_goals, 0) if home == "A" else (0, a_goals) if away == "A" else (1, 1)
                        games.append(_match(label, day, home, away, gf, ga))
                        day += 1
        return games

    pool = [g for i, label in enumerate(("2020-21", "2021-22", "2022-23"))
            for g in season(label, 1000 + i * 365, 0)]
    pool += season("2023-24", 2200, 4)

    rows = season_fit.replay_season(pool, "2023-24", DixonColesModel, horizons=(0,))
    last_a_home = next(r for r in reversed(rows) if r["home"] == "A")
    assert last_a_home["rolling"][0]["probs"][0] > last_a_home["frozen"]["probs"][0]


def _new_club_league(new_club_games):
    """Four clubs with a long history, plus a new one that has won every game it has played."""
    clubs = ["A", "B", "C", "D"]
    games = [_match("2023-24", 1000 + i * 3, h, a, 1 + (i % 2), i % 3)
             for i, (h, a) in enumerate((h, a) for _ in range(6) for h in clubs for a in clubs if h != a)]
    games += [_match("2023-24", 1400 + i, "N", clubs[i % 4], 5, 0) for i in range(new_club_games)]
    return games


def test_the_candidate_is_the_setting_that_was_fixed_before_the_held_out_run():
    engine = season_fit.CandidateEngine()
    assert (engine.half_life_days, engine.min_games) == (270.0, 10)


def test_a_club_below_ten_games_has_the_default_rating_and_at_ten_its_own():
    """A club the fit has barely seen is rated exactly like a club it has never seen."""
    nine = season_fit.CandidateEngine().fit(_new_club_league(9))
    assert nine.expected_goals("N", "A") == nine.expected_goals("Never seen", "A")

    ten = season_fit.CandidateEngine().fit(_new_club_league(10))
    assert ten.expected_goals("N", "A")[0] > ten.expected_goals("Never seen", "A")[0]


def test_the_guard_leaves_established_clubs_exactly_as_the_engine_rates_them():
    games = _new_club_league(0)
    guarded = season_fit.CandidateEngine().fit(games)
    plain = DixonColesModel(half_life_days=270.0).fit(games)
    assert guarded.expected_goals("A", "B") == plain.expected_goals("A", "B")
