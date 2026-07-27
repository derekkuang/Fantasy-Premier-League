"""Walk-forward validation of the xP model against realized FPL points.

For each gameweek N (after a burn-in), the model uses ONLY data from GWs < N — rolling
per-90 rates and a match engine refit on fixtures before N — to predict each player's
points, then scores that against the realized `total_points`. FPL's own `xP` is the
baseline to beat. This is what turns the FPL layer from "asserted" to "validated".

Point-in-time is enforced structurally: GW N is scored BEFORE its rows are added to the
rolling accumulator, and the engine trains only on fixtures with gw < N.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime

from ..models.dixon_coles import DixonColesModel
from ..models.minutes import MinutesModel
from ..models.shares import rate_shares
from ..models.xpoints import (
    PlayerContext,
    dc_point_probability,
    expected_bonus,
    expected_points,
)


def _ordinal(iso: str) -> int:
    return datetime.strptime((iso or "1970-01-01")[:10], "%Y-%m-%d").date().toordinal()


def _per90(total: float, minutes: float, min_minutes: int) -> float:
    return total / (minutes / 90.0) if minutes >= min_minutes else 0.0


def validate_xp(
    player_rows: Sequence[dict],
    fixtures: Sequence[dict],
    teams_name_to_id: dict,
    burn_in: int = 8,
    half_life_days: float = 180.0,
    min_rate_minutes: int = 270,
    minutes_mode: str = "recent",
    xg_mode: str = "season",
    return_records: bool = False,
):
    """Walk-forward score of model xP vs realized points, with FPL's xP as the baseline.

    With return_records=True, also returns the raw (gw, element, my_xp, fpl_xp, actual, pos)
    tuples — used by the point-in-time leakage test.
    """
    import scipy.stats as st  # noqa: PLC0415

    for fx in fixtures:
        fx["date_ord"] = _ordinal(fx["kickoff"])
    fixtures = sorted(fixtures, key=lambda f: f["gw"])

    # group player rows: gw -> element -> [rows] (a list handles double gameweeks)
    by_gw: dict = defaultdict(lambda: defaultdict(list))
    for r in player_rows:
        tid = teams_name_to_id.get(r["team"])
        if tid is None:
            continue
        r["team_id"] = tid
        by_gw[r["gw"]][r["element"]].append(r)

    minutes_model = MinutesModel()

    def _mp(a):  # noqa: ANN001 — minutes prediction under the chosen mode
        if minutes_mode == "recent":
            return minutes_model.from_recent(a["recent"][-6:])
        return minutes_model.from_season(a["minutes"], a["starts"], max(a["games"], 1))

    def _rate(a, key, half_life=4.0):  # noqa: ANN001 — per-90 xg/xa rate under the chosen mode
        if xg_mode == "recent":
            vals, mins = a[f"recent_{key}"], a["recent"]
            m = len(vals)
            w = [0.5 ** ((m - 1 - i) / half_life) for i in range(m)]
            den = sum(wi * mm for wi, mm in zip(w, mins, strict=True))
            if den < 90.0:  # not enough weighted minutes to trust a rate
                return 0.0
            return sum(wi * v for wi, v in zip(w, vals, strict=True)) / (den / 90.0)
        return a[key] / (a["minutes"] / 90.0) if a["minutes"] >= min_rate_minutes else 0.0

    acc: dict = {}  # element -> rolling totals (from GWs strictly before the current one)
    records = []    # (gw, element, my_xp, fpl_xp, actual, position, minutes)

    for n in sorted(by_gw):
        if n > burn_in and acc:
            engine = DixonColesModel(half_life_days).fit([f for f in fixtures if f["gw"] < n])
            xmins = {el: _mp(a).x_minutes for el, a in acc.items()}
            players = [
                {"code": el, "team_id": a["team_id"], "xg90": _rate(a, "xg"), "xa90": _rate(a, "xa")}
                for el, a in acc.items()
            ]
            shares = rate_shares(players, xmins)

            for el, rows in by_gw[n].items():
                a = acc.get(el)
                if not a or a["games"] == 0:
                    continue
                mp = _mp(a)
                sh = shares.get(el, {"goal_share": 0.0, "assist_share": 0.0})
                dc90 = _per90(a["dc"], a["minutes"], min_rate_minutes)
                bon90 = _per90(a["bonus"], a["minutes"], min_rate_minutes)
                pos, tid = rows[0]["position"], rows[0]["team_id"]

                my_xp, scored = 0.0, False
                for r in rows:  # sum over the team's fixtures this GW (usually one)
                    opp = r["opponent_team"]
                    if not (engine.knows(str(tid)) and engine.knows(str(opp))):
                        continue
                    if r["was_home"]:
                        pr = engine.predict(str(tid), str(opp))
                        lam, p_cs, opp_lam = pr.lam_home, pr.clean_sheet_home, pr.lam_away
                    else:
                        pr = engine.predict(str(opp), str(tid))
                        lam, p_cs, opp_lam = pr.lam_away, pr.clean_sheet_away, pr.lam_home
                    ctx = PlayerContext(
                        position=pos, p_play=mp.p_play, p_60=mp.p_60, team_lambda=lam,
                        goal_share=sh["goal_share"], assist_share=sh["assist_share"],
                        p_clean_sheet=p_cs,
                        x_saves=(opp_lam * 3.0 * (mp.x_minutes / 90.0) if pos == "GK" else 0.0),
                        p_dc_point=dc_point_probability(dc90, mp.x_minutes, pos),
                        x_bonus=expected_bonus(bon90, mp.x_minutes),
                    )
                    my_xp += expected_points(ctx)
                    scored = True
                if scored:
                    records.append(
                        (n, el, my_xp, sum(r["fpl_xp"] for r in rows),
                         sum(r["total_points"] for r in rows), pos,
                         sum(r["minutes"] for r in rows))
                    )

        # accumulate GW N AFTER scoring it (point-in-time)
        for el, rows in by_gw[n].items():
            a = acc.setdefault(
                el,
                {"minutes": 0, "starts": 0, "xg": 0.0, "xa": 0.0, "dc": 0, "bonus": 0, "games": 0,
                 "recent": [], "recent_xg": [], "recent_xa": [], "team_id": rows[0]["team_id"]},
            )
            a["team_id"] = rows[0]["team_id"]
            a["games"] += len(rows)
            a["recent"].append(sum(r["minutes"] for r in rows))       # per-GW minutes (recency)
            a["recent_xg"].append(sum(r["xg"] for r in rows))         # per-GW xG (recency)
            a["recent_xa"].append(sum(r["xa"] for r in rows))         # per-GW xA (recency)
            for r in rows:
                a["minutes"] += r["minutes"]
                a["starts"] += r["starts"]
                a["xg"] += r["xg"]
                a["xa"] += r["xa"]
                a["dc"] += r["dc"]
                a["bonus"] += r["bonus"]

    metrics = _score(records, st)
    return (metrics, records) if return_records else metrics


def _subset_metrics(recs, st) -> dict | None:  # noqa: ANN001
    """MAE + per-GW Spearman for model and FPL over a record subset. record indices:
    (gw=0, element=1, my_xp=2, fpl_xp=3, actual=4, pos=5, minutes=6)."""
    if not recs:
        return None
    my = [r[2] for r in recs]
    fpl = [r[3] for r in recs]
    act = [r[4] for r in recs]

    per_gw: dict = defaultdict(list)
    for r in recs:
        per_gw[r[0]].append(r)
    sp_m, sp_f, beat, compared = [], [], 0, 0
    for g in per_gw.values():
        if len(g) < 10:  # too few players to rank-correlate meaningfully
            continue
        compared += 1
        m, f, a = [r[2] for r in g], [r[3] for r in g], [r[4] for r in g]
        sm, sf = st.spearmanr(m, a).correlation, st.spearmanr(f, a).correlation
        if sm == sm:
            sp_m.append(sm)
        if sf == sf:
            sp_f.append(sf)
        mm = statistics.mean(abs(x - y) for x, y in zip(m, a, strict=True))
        mf = statistics.mean(abs(x - y) for x, y in zip(f, a, strict=True))
        beat += mm <= mf

    return {
        "n": len(recs),
        "mae_model": statistics.mean(abs(x - y) for x, y in zip(my, act, strict=True)),
        "mae_fpl": statistics.mean(abs(x - y) for x, y in zip(fpl, act, strict=True)),
        "gw_spearman_model": statistics.mean(sp_m) if sp_m else None,
        "gw_spearman_fpl": statistics.mean(sp_f) if sp_f else None,
        "gws_model_mae_beats_fpl": f"{beat}/{compared}",  # denominator matches numerator
    }


def _score(records, st) -> dict:  # noqa: ANN001
    if not records:
        return {"n": 0}
    played = [r for r in records if r[6] > 0]  # players who actually featured
    pos_mae = {}
    for p in ("GK", "DEF", "MID", "FWD"):
        sub = [(r[2], r[4]) for r in played if r[5] == p]
        if sub:
            pos_mae[p] = statistics.mean(abs(x - y) for x, y in sub)
    return {
        "n": len(records),
        "gws_scored": len({r[0] for r in records}),
        "all_players": _subset_metrics(records, st),
        "played_only": _subset_metrics(played, st),  # the honest "who to pick" test
        "mae_by_position_played": pos_mae,
    }
