"""Walk-forward validation of the xP model against realized FPL points.

For each gameweek N (after a burn-in), the model uses ONLY data from GWs < N — rolling
per-90 rates and a match engine refit on fixtures before N — to predict each player's
points, then scores that against the realized `total_points`. FPL's own `xP` is the
baseline to beat. This is what turns the FPL layer from "asserted" to "validated".

Point-in-time is enforced structurally: GW N is scored BEFORE its rows are added to the
rolling accumulator, and the engine trains only on fixtures with gw < N.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime

from ..models import saves as saves_model
from ..models.dixon_coles import DixonColesModel
from ..models.minutes import MinutesModel
from ..models.shares import rate_shares
from ..models.xpoints import (
    PlayerContext,
    bonus_from_returns,
    dc_point_probability,
    expected_bonus,
    expected_conceded_penalty,
    expected_points,
)


def _ordinal(iso: str) -> int:
    return datetime.strptime((iso or "1970-01-01")[:10], "%Y-%m-%d").date().toordinal()


def _per90(total: float, minutes: float, min_minutes: int) -> float:
    return total / (minutes / 90.0) if minutes >= min_minutes else 0.0


class _OracleMinutes:
    """A minutes prediction that already knows the answer. CHEATING, on purpose.

    `oracle_minutes=True` replaces the minutes model with the minutes actually played, which
    makes the walk-forward no longer point-in-time and its output no longer a validation number.
    It exists to price a decision: perfect team-news is the ceiling any lineup feed — a paid
    expected-lineups API, a scraped predicted XI — is buying a fraction of. Without the ceiling
    there is no way to judge whether 84%-accurate lineups are worth a subscription, and the
    honest answer might be no.

    IT IS A LOWER BOUND, not the true ceiling. Goal and assist shares are allocated across a
    squad by `rate_shares` BEFORE this substitution happens, using the model's expected minutes,
    so the largest term in an attacker's projection still runs on a guess. Only appearance,
    clean sheet (through p_60), saves, defensive contribution and bonus get the real number.
    Perfect team news is worth strictly more than this measures.

    Never call this from anything that reports accuracy.
    """

    __slots__ = ("p_60", "p_play", "x_minutes")

    def __init__(self, minutes: float):
        self.x_minutes = float(minutes)
        self.p_play = 1.0 if minutes > 0 else 0.0
        self.p_60 = 1.0 if minutes >= 60 else 0.0


def _x_saves(pos, mode, rates, team_id, opp_id, opp_lambda, x_minutes):  # noqa: ANN001
    """Expected saves under the selected model.

    "lambda" is the shipped behaviour: saves proportional to expected goals conceded, which
    puts save points and clean-sheet points in direct opposition. "shots" uses observed saves
    faced (see `models.saves`). Falls back to "lambda" when there is no history yet, so the
    opening gameweeks of a walk-forward behave identically under both modes rather than
    scoring a keeper at zero.
    """
    if pos != "GK":
        return 0.0
    if rates is not None:
        if mode == "shots":
            return rates.expected_saves(team_id, opp_id, x_minutes)
        if mode == "hybrid":
            # The team's own tendency to keep its keeper busy (empirical, absent from
            # "lambda") times THIS fixture's opponent strength from the engine (absent from
            # "shots", which only knows the opponent's season-long average).
            return rates.expected_saves_vs_lambda(team_id, opp_lambda, x_minutes)
    return opp_lambda * 3.0 * (x_minutes / 90.0)


def validate_xp(
    player_rows: Sequence[dict],
    fixtures: Sequence[dict],
    teams_name_to_id: dict,
    burn_in: int = 8,
    half_life_days: float = 180.0,
    min_rate_minutes: int = 270,
    minutes_mode: str = "recent",
    xg_mode: str = "season",
    bonus_mode: str = "rate",
    saves_mode: str = "lambda",
    match_saves: Sequence[dict] | None = None,
    oracle_minutes: bool = False,
    return_records: bool = False,
    fixture_lambdas: dict | None = None,
):
    """Walk-forward score of model xP vs realized points, with FPL's xP as the baseline.

    With return_records=True, also returns the raw (gw, element, my_xp, fpl_xp, actual, pos)
    tuples — used by the point-in-time leakage test.

    THE BASELINE IS `fpl_xp_prev`, NOT `fpl_xp`. The shipped `xP` column is scraped after the
    gameweek and absorbs that gameweek's points through FPL's `form` average, so scoring
    against it compares a forecast to something that has already seen the answer. See
    `ingest.vaastav._add_clean_baseline`. Rows predating that field fall back to `fpl_xp` and
    are flagged by `baseline_clean` in the result.
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

    baseline_clean = True   # set False if a legacy caller supplies no shifted column
    acc: dict = {}  # element -> rolling totals (from GWs strictly before the current one)
    records = []    # (gw, element, my_xp, fpl_xp, actual, position, minutes)

    # Saves-from-shots-faced (saves_mode="shots"). Accumulated under the SAME point-in-time
    # rule as everything else: a gameweek's matches are folded in only after that gameweek has
    # been scored, so the rates predicting GW N are built from GWs < N.
    saves_by_gw: dict = defaultdict(list)
    for m in match_saves or []:
        saves_by_gw[m["gw"]].append(m)
    save_counts: dict = {}
    saves_rates = None

    for n in sorted(by_gw):
        if saves_mode in ("shots", "hybrid"):
            saves_rates = saves_model.SavesRates.build(save_counts) if save_counts else None
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
                if oracle_minutes:
                    mp = _OracleMinutes(sum(r["minutes"] for r in rows))
                sh = shares.get(el, {"goal_share": 0.0, "assist_share": 0.0})
                dc90 = _per90(a["dc"], a["minutes"], min_rate_minutes)
                bon90 = _per90(a["bonus"], a["minutes"], min_rate_minutes)
                pos, tid = rows[0]["position"], rows[0]["team_id"]

                my_xp, scored = 0.0, False
                for r in rows:  # sum over the team's fixtures this GW (usually one)
                    opp = r["opponent_team"]
                    home_id, away_id = (tid, opp) if r["was_home"] else (opp, tid)
                    mkt = fixture_lambdas.get((home_id, away_id)) if fixture_lambdas else None
                    if mkt is not None:
                        # market-implied lambdas for this fixture; clean sheet ~ P(opp scores 0)
                        lam_h, lam_a = mkt
                        if r["was_home"]:
                            lam, opp_lam, p_cs = lam_h, lam_a, math.exp(-lam_a)
                        else:
                            lam, opp_lam, p_cs = lam_a, lam_h, math.exp(-lam_h)
                    elif not (engine.knows(str(tid)) and engine.knows(str(opp))):
                        continue
                    elif r["was_home"]:
                        pr = engine.predict(str(tid), str(opp))
                        lam, p_cs, opp_lam = pr.lam_home, pr.clean_sheet_home, pr.lam_away
                    else:
                        pr = engine.predict(str(opp), str(tid))
                        lam, p_cs, opp_lam = pr.lam_away, pr.clean_sheet_away, pr.lam_home
                    p_dc = dc_point_probability(dc90, mp.x_minutes, pos)
                    if bonus_mode == "returns":
                        x_bonus = bonus_from_returns(
                            sh["goal_share"] * lam, sh["assist_share"] * lam, p_cs * mp.p_60, p_dc
                        )
                    else:
                        x_bonus = expected_bonus(bon90, mp.x_minutes)
                    ctx = PlayerContext(
                        position=pos, p_play=mp.p_play, p_60=mp.p_60, team_lambda=lam,
                        goal_share=sh["goal_share"], assist_share=sh["assist_share"],
                        p_clean_sheet=p_cs,
                        x_saves=_x_saves(
                            pos, saves_mode, saves_rates, tid, opp, opp_lam, mp.x_minutes
                        ),
                        p_dc_point=p_dc, x_bonus=x_bonus,
                        opp_lambda=opp_lam,
                        x_conceded_penalty=(
                            expected_conceded_penalty(opp_lam, mp.x_minutes)
                            if pos in ("GK", "DEF") else 0.0
                        ),
                    )
                    my_xp += expected_points(ctx)
                    scored = True
                if scored:
                    # Three cases, kept distinct on purpose:
                    #   key absent   -> a caller that predates the shift (tests, legacy);
                    #                   fall back to the raw column and say so via
                    #                   `baseline_clean=False` rather than dropping the data.
                    #   key is None  -> a player's FIRST gameweek. No prior forecast exists,
                    #                   so there is nothing to compare against; skip the row
                    #                   rather than score the baseline against an implicit 0.
                    #   key is a num -> the clean pre-deadline forecast. Use it.
                    if "fpl_xp_prev" not in rows[0]:
                        fpl_clean = sum(r["fpl_xp"] for r in rows)
                        baseline_clean = False
                    else:
                        prevs = [r.get("fpl_xp_prev") for r in rows]
                        if all(p is None for p in prevs):
                            continue
                        fpl_clean = sum(p for p in prevs if p is not None)
                        baseline_clean = True
                    records.append(
                        (n, el, my_xp, fpl_clean,
                         sum(r["total_points"] for r in rows), pos,
                         sum(r["minutes"] for r in rows))
                    )

        # accumulate GW N AFTER scoring it (point-in-time)
        for m in saves_by_gw.get(n, []):
            saves_model.accumulate(
                save_counts, m["home"], m["away"],
                m["home_keeper_saves"], m["away_keeper_saves"],
            )
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
    metrics["baseline_clean"] = baseline_clean
    return (metrics, records) if return_records else metrics


def validate_multi_gw(records, window: int = 3, min_players: int = 10) -> dict:  # noqa: ANN001
    """Score a multi-GW outlook: sum each player's model xP and FPL xP over rolling `window`
    gameweeks and rank against their realized summed points (played players only).

    FPL publishes no multi-GW number, so the honest baseline is FPL's OWN xP summed over the
    same window. Returns per-start-GW-averaged Spearman + MAE for model and FPL — i.e. "if you
    pick on a `window`-week outlook, whose sum ranks the real `window`-week output better?".
    records: the (gw, element, my_xp, fpl_xp, actual, pos, minutes) tuples from validate_xp.
    """
    import scipy.stats as st  # noqa: PLC0415

    by = {(r[0], r[1]): r for r in records}
    gws = sorted({r[0] for r in records})
    sp_m, sp_f, mae_m, mae_f, n = [], [], [], [], 0
    for start in gws:
        window_gws = [start + i for i in range(window)]
        if window_gws[-1] > gws[-1]:
            continue
        rows = []
        for el in {r[1] for r in records if r[0] == start}:
            recs = [by.get((wg, el)) for wg in window_gws]
            if any(x is None for x in recs) or sum(x[6] for x in recs) <= 0:
                continue  # need a record each GW of the window, and some minutes played
            rows.append((sum(x[2] for x in recs), sum(x[3] for x in recs), sum(x[4] for x in recs)))
        if len(rows) < min_players:
            continue
        m, f, a = [r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows]
        sm, sf = st.spearmanr(m, a).correlation, st.spearmanr(f, a).correlation
        if sm == sm:
            sp_m.append(sm)
        if sf == sf:
            sp_f.append(sf)
        mae_m.append(statistics.mean(abs(x - y) for x, y in zip(m, a, strict=True)))
        mae_f.append(statistics.mean(abs(x - y) for x, y in zip(f, a, strict=True)))
        n += len(rows)

    mean = lambda xs: statistics.mean(xs) if xs else None  # noqa: E731
    return {
        "window": window, "windows_scored": len(sp_m), "n": n,
        "gw_spearman_model": mean(sp_m), "gw_spearman_fpl": mean(sp_f),
        "mae_model": mean(mae_m), "mae_fpl": mean(mae_f),
    }


def _subset_metrics(recs, st) -> dict | None:  # noqa: ANN001
    """MAE + per-GW Spearman for model and FPL over a record subset. record indices:
    (gw=0, element=1, my_xp=2, fpl_xp=3, actual=4, pos=5, minutes=6)."""
    if not recs:
        return None
    my = [r[2] for r in recs]
    act = [r[4] for r in recs]

    per_gw: dict = defaultdict(list)
    for r in recs:
        per_gw[r[0]].append(r)
    # THE BASELINE IS OFTEN ABSENT, AND THAT USED TO BE HIDDEN.
    #
    # vaastav's `xP` column is not populated for every gameweek — in 2025-26 it carries real
    # values for four of thirty, and is a column of zeros for the rest. The earlier version of
    # this function appended our Spearman whenever ours was defined and FPL's whenever theirs
    # was, which silently averaged the two over DIFFERENT gameweek sets: ours over all thirty,
    # theirs over the four. It also took FPL's MAE across every record, so 86% of that average
    # was |0 − actual| — a comparison against a column of zeros, which our model duly "beat".
    #
    # Both numbers went onto a public page claiming to publish how well the model does. So:
    # a gameweek now counts only when BOTH predictors are defined on it, MAE is computed on
    # exactly those records, and `baseline_gws` reports how thin the comparison is.
    sp_m, sp_f, beat, compared = [], [], 0, 0
    common: list = []
    for g in per_gw.values():
        if len(g) < 10:  # too few players to rank-correlate meaningfully
            continue
        m, f, a = [r[2] for r in g], [r[3] for r in g], [r[4] for r in g]
        sm, sf = st.spearmanr(m, a).correlation, st.spearmanr(f, a).correlation
        if not (sm == sm and sf == sf):   # either side undefined => not a comparison
            continue
        compared += 1
        common.extend(g)
        sp_m.append(sm)
        sp_f.append(sf)
        mm = statistics.mean(abs(x - y) for x, y in zip(m, a, strict=True))
        mf = statistics.mean(abs(x - y) for x, y in zip(f, a, strict=True))
        beat += mm <= mf

    # Our own error is still worth reporting over everything we scored; FPL's is only
    # meaningful where FPL actually predicted something.
    return {
        "n": len(recs),
        "mae_model": statistics.mean(abs(x - y) for x, y in zip(my, act, strict=True)),
        "mae_model_common": statistics.mean(abs(r[2] - r[4]) for r in common) if common else None,
        "mae_fpl": statistics.mean(abs(r[3] - r[4]) for r in common) if common else None,
        "gw_spearman_model": statistics.mean(sp_m) if sp_m else None,
        "gw_spearman_fpl": statistics.mean(sp_f) if sp_f else None,
        "gws_model_mae_beats_fpl": f"{beat}/{compared}",
        "baseline_gws": compared,          # how many gameweeks the comparison rests on
        "baseline_n": len(common),
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
