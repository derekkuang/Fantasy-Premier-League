"""LightGBM points model — LEARN total_points from point-in-time features.

The structured xP model plateaued at ~0.33 played-only Spearman (three null tweaks). This
takes a different paradigm: train a gradient-boosted regressor on the vaastav per-gameweek
history to learn the points function directly, capturing interactions the hand-built
assembly can't. It is scored on the SAME validation harness (`eval.fpl_backtest._score`) so
it is directly comparable to the structured xP and to FPL's own xP.

Point-in-time is enforced exactly as in the structured harness: a gameweek's rows are used
for a prediction only after it has been added to the rolling accumulator, the engine trains
on fixtures before the gameweek, and (in the walk-forward) the model trains only on earlier
gameweeks. The structured xP is itself a feature, so the model starts from it and corrects.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime

from .dixon_coles import DixonColesModel
from .minutes import MinutesModel
from .shares import rate_shares
from .xpoints import PlayerContext, dc_point_probability, expected_bonus, expected_points

FEATURES = [
    "xg90", "xa90", "dc90", "bonus90", "min_per_game", "start_rate", "ppg", "games",
    "team_lambda", "opp_lambda", "p_cs", "x_minutes", "structured_xp", "was_home", "pos_code",
]
_POS_CODE = {"GK": 0, "DEF": 1, "MID": 2, "FWD": 3}
_CAT_FEATURE = "pos_code"


def _ordinal(iso: str) -> int:
    return datetime.strptime((iso or "1970-01-01")[:10], "%Y-%m-%d").date().toordinal()


def extract_features(
    player_rows: Sequence[dict],
    fixtures: Sequence[dict],
    teams_name_to_id: dict,
    burn_in: int = 8,
    half_life_days: float = 180.0,
    min_rate_minutes: int = 270,
) -> list[dict]:
    """One feature row per scored player-gameweek, all point-in-time (from GWs < n)."""
    for fx in fixtures:
        fx["date_ord"] = _ordinal(fx["kickoff"])
    fixtures = sorted(fixtures, key=lambda f: f["gw"])

    by_gw: dict = defaultdict(lambda: defaultdict(list))
    for r in player_rows:
        tid = teams_name_to_id.get(r["team"])
        if tid is None:
            continue
        r["team_id"] = tid
        by_gw[r["gw"]][r["element"]].append(r)

    mm = MinutesModel()
    acc: dict = {}
    out: list[dict] = []

    def rate(a, key):  # noqa: ANN001
        return a[key] / (a["minutes"] / 90.0) if a["minutes"] >= min_rate_minutes else 0.0

    for n in sorted(by_gw):
        if n > burn_in and acc:
            engine = DixonColesModel(half_life_days).fit([f for f in fixtures if f["gw"] < n])
            xmins = {el: mm.from_recent(a["recent"][-6:]).x_minutes for el, a in acc.items()}
            players = [
                {"code": el, "team_id": a["team_id"], "xg90": rate(a, "xg"), "xa90": rate(a, "xa")}
                for el, a in acc.items()
            ]
            shares = rate_shares(players, xmins)

            for el, rows in by_gw[n].items():
                a = acc.get(el)
                if not a or a["games"] == 0:
                    continue
                mp = mm.from_recent(a["recent"][-6:])
                sh = shares.get(el, {"goal_share": 0.0, "assist_share": 0.0})
                dc90, bon90 = rate(a, "dc"), rate(a, "bonus")
                pos, tid = rows[0]["position"], rows[0]["team_id"]

                sxp, team_lam, opp_lam, p_cs, was_home, nf = 0.0, 0.0, 0.0, 0.0, 0, 0
                for r in rows:  # sum over the GW's fixtures (double GW)
                    opp = r["opponent_team"]
                    if not (engine.knows(str(tid)) and engine.knows(str(opp))):
                        continue
                    if r["was_home"]:
                        pr = engine.predict(str(tid), str(opp))
                        lam, cs, ol = pr.lam_home, pr.clean_sheet_home, pr.lam_away
                        was_home = 1
                    else:
                        pr = engine.predict(str(opp), str(tid))
                        lam, cs, ol = pr.lam_away, pr.clean_sheet_away, pr.lam_home
                    pdc = dc_point_probability(dc90, mp.x_minutes, pos)
                    ctx = PlayerContext(
                        position=pos, p_play=mp.p_play, p_60=mp.p_60, team_lambda=lam,
                        goal_share=sh["goal_share"], assist_share=sh["assist_share"], p_clean_sheet=cs,
                        x_saves=(ol * 3.0 * (mp.x_minutes / 90.0) if pos == "GK" else 0.0),
                        p_dc_point=pdc, x_bonus=expected_bonus(bon90, mp.x_minutes),
                    )
                    sxp += expected_points(ctx)
                    team_lam, opp_lam, p_cs, nf = team_lam + lam, opp_lam + ol, cs, nf + 1
                if nf == 0:
                    continue

                out.append(
                    {
                        "gw": n, "element": el, "position": pos,
                        "target": sum(r["total_points"] for r in rows),
                        "fpl_xp": sum(r["fpl_xp"] for r in rows),
                        "minutes": sum(r["minutes"] for r in rows),
                        "xg90": rate(a, "xg"), "xa90": rate(a, "xa"), "dc90": dc90, "bonus90": bon90,
                        "min_per_game": a["minutes"] / a["games"], "start_rate": a["starts"] / a["games"],
                        "ppg": a["points"] / a["games"], "games": a["games"],
                        "team_lambda": team_lam, "opp_lambda": opp_lam, "p_cs": p_cs,
                        "x_minutes": mp.x_minutes, "structured_xp": sxp,
                        "was_home": was_home, "pos_code": _POS_CODE[pos],
                    }
                )

        for el, rows in by_gw[n].items():  # accumulate AFTER scoring (point-in-time)
            a = acc.setdefault(
                el,
                {"minutes": 0, "starts": 0, "xg": 0.0, "xa": 0.0, "dc": 0, "bonus": 0,
                 "points": 0, "games": 0, "recent": [], "team_id": rows[0]["team_id"]},
            )
            a["team_id"] = rows[0]["team_id"]
            a["games"] += len(rows)
            a["recent"].append(sum(r["minutes"] for r in rows))
            for r in rows:
                a["minutes"] += r["minutes"]
                a["starts"] += r["starts"]
                a["xg"] += r["xg"]
                a["xa"] += r["xa"]
                a["dc"] += r["dc"]
                a["bonus"] += r["bonus"]
                a["points"] += r["total_points"]
    return out


def walk_forward_lgbm(
    feat_rows: Sequence[dict], min_train: int = 2000, objective: str = "regression"
) -> list[tuple]:
    """Walk-forward: for each gameweek, train LightGBM on all earlier rows and predict it.

    objective="regression" (L2) predicts points; objective="rank" uses rank_xendcg grouped by
    gameweek, which optimises within-GW RANKING directly (what per-GW Spearman measures).
    Returns records in the harness's (gw, element, pred, fpl_xp, actual, pos, minutes) shape.
    """
    import lightgbm as lgb  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    rows = sorted(feat_rows, key=lambda r: r["gw"])  # gw-sorted so rank groups align
    cat_idx = FEATURES.index(_CAT_FEATURE)

    records = []
    for n in sorted({r["gw"] for r in rows}):
        train = [r for r in rows if r["gw"] < n]
        test = [r for r in rows if r["gw"] == n]
        if len(train) < min_train or not test:
            continue
        x_tr = np.array([[r[f] for f in FEATURES] for r in train], dtype=float)
        x_te = np.array([[r[f] for f in FEATURES] for r in test], dtype=float)

        if objective == "rank":
            y_tr = np.clip([r["target"] for r in train], 0, None)  # relevance >= 0
            gw_counts = defaultdict(int)
            for r in train:
                gw_counts[r["gw"]] += 1
            groups = [gw_counts[g] for g in sorted(gw_counts)]  # one query group per GW
            dtrain = lgb.Dataset(x_tr, y_tr, group=groups, categorical_feature=[cat_idx])
            params = {"objective": "rank_xendcg", "num_leaves": 31, "learning_rate": 0.05,
                      "min_data_in_leaf": 50, "verbose": -1}
        else:
            y_tr = np.array([r["target"] for r in train], dtype=float)
            dtrain = lgb.Dataset(x_tr, y_tr, categorical_feature=[cat_idx])
            params = {"objective": "regression_l2", "num_leaves": 31, "learning_rate": 0.05,
                      "min_data_in_leaf": 50, "feature_fraction": 0.9, "bagging_fraction": 0.8,
                      "bagging_freq": 1, "verbose": -1}

        model = lgb.train(params, dtrain, num_boost_round=200)
        for r, pred in zip(test, model.predict(x_te), strict=True):
            records.append((n, r["element"], float(pred), r["fpl_xp"], r["target"], r["position"], r["minutes"]))
    return records


def structured_records(feat_rows: Sequence[dict], only_gws=None) -> list[tuple]:
    """The structured xP as harness records, on the same rows — the A/B baseline."""
    return [
        (r["gw"], r["element"], r["structured_xp"], r["fpl_xp"], r["target"], r["position"], r["minutes"])
        for r in feat_rows
        if only_gws is None or r["gw"] in only_gws
    ]
