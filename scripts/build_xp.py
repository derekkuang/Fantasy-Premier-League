#!/usr/bin/env python3
"""Build the expected-points (xP) table for the upcoming gameweek.

Pipeline: fit Dixon-Coles on historical results -> map FPL team names to the engine's
Football-Data names -> distribute team goals to players via minutes-aware per-90 shares ->
add clean sheets, GK saves, expected BONUS (per-90 rate) and expected DEFENSIVE-CONTRIBUTION
points (Poisson-tail over the position threshold) -> apply the minutes model -> rank by xP,
and by RANK-relative value (differential value + a differential-adjusted captain pick).

Honest caveats (printed): promoted teams have no engine history / reliable shares (excluded);
new signings carry their previous club's output; near-deadline team news not yet ingested.

Usage: python scripts/build_xp.py
"""

from __future__ import annotations

import pathlib
import sys
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpledge import config  # noqa: E402
from fpledge.ingest import footballdata  # noqa: E402
from fpledge.models import rank  # noqa: E402
from fpledge.models.dixon_coles import DixonColesModel  # noqa: E402
from fpledge.models.minutes import MinutesModel  # noqa: E402
from fpledge.models.shares import match_shares, team_minutes  # noqa: E402
from fpledge.models.teammap import build_team_map  # noqa: E402
from fpledge.models.xpoints import (  # noqa: E402
    PlayerContext,
    dc_point_probability,
    expected_bonus,
    expected_points,
)
from fpledge.storage import duck  # noqa: E402

SEASONS = ["2324", "2425", "2526"]
UPCOMING_GW = 1
LOW_COVERAGE = 9000  # current-squad last-season minutes below this -> shares unreliable
MIN_RATE_MINUTES = 270  # need this many last-season minutes to trust a per-90 rate
PLAYER_COLS = [
    "code", "team_id", "position", "web_name", "minutes", "starts",
    "xg", "xa", "dc", "bonus", "ownership",
]


def main() -> None:
    con = duck.connect()
    duck.init_schema(con)
    players = [
        dict(zip(PLAYER_COLS, r, strict=True))
        for r in con.execute(
            f"SELECT {', '.join(PLAYER_COLS)} FROM player_season WHERE season = ?",
            [config.SEASON],
        ).fetchall()
    ]
    if not players:
        print("no player_season data — run scripts/pull_player_history.py first.")
        con.close()
        return
    fpl_teams = {
        tid: name
        for tid, name in con.execute(
            "SELECT team_id, name FROM teams WHERE season = ?", [config.SEASON]
        ).fetchall()
    }
    fixtures = con.execute(
        "SELECT home_id, away_id FROM fixtures WHERE season = ? AND gw = ?",
        [config.SEASON, UPCOMING_GW],
    ).fetchall()
    con.close()

    print("fitting Dixon-Coles on historical results...")
    matches = footballdata.load_seasons(SEASONS)
    engine = DixonColesModel(half_life_days=180).fit(matches)
    fd_names = sorted({m["home"] for m in matches} | {m["away"] for m in matches})
    tmap = build_team_map(list(fpl_teams.values()), fd_names)

    minutes_model = MinutesModel()
    minutes_pred = {p["code"]: minutes_model.from_season(p["minutes"], p["starts"]) for p in players}
    x_minutes = {code: mp.x_minutes for code, mp in minutes_pred.items()}
    shares = match_shares(players, x_minutes)
    coverage = team_minutes(players)
    by_team: dict = defaultdict(list)
    for p in players:
        by_team[p["team_id"]].append(p)

    rows, skipped = [], []
    for home_id, away_id in fixtures:
        home_fd, away_fd = tmap.get(fpl_teams.get(home_id)), tmap.get(fpl_teams.get(away_id))
        if not (home_fd and away_fd and engine.knows(home_fd) and engine.knows(away_fd)):
            skipped.append((fpl_teams.get(home_id), fpl_teams.get(away_id)))
            continue
        pred = engine.predict(home_fd, away_fd)
        sides = [
            (home_id, pred.lam_home, pred.clean_sheet_home, pred.lam_away),
            (away_id, pred.lam_away, pred.clean_sheet_away, pred.lam_home),
        ]
        for team_id, team_lambda, p_cs, opp_lambda in sides:
            low_cov = coverage.get(team_id, 0) < LOW_COVERAGE
            for p in by_team.get(team_id, []):
                mp = minutes_pred[p["code"]]
                sh = shares.get(p["code"], {"goal_share": 0.0, "assist_share": 0.0})
                per90 = p["minutes"] / 90.0
                trust = p["minutes"] >= MIN_RATE_MINUTES
                dc_per90 = (p["dc"] / per90) if trust else 0.0
                bonus_per90 = (p["bonus"] / per90) if trust else 0.0
                ctx = PlayerContext(
                    position=p["position"],
                    p_play=mp.p_play,
                    p_60=mp.p_60,
                    team_lambda=team_lambda,
                    goal_share=sh["goal_share"],
                    assist_share=sh["assist_share"],
                    p_clean_sheet=p_cs,
                    x_saves=(opp_lambda * 3.0 * (mp.x_minutes / 90.0) if p["position"] == "GK" else 0.0),
                    p_dc_point=dc_point_probability(dc_per90, mp.x_minutes, p["position"]),
                    x_bonus=expected_bonus(bonus_per90, mp.x_minutes),
                )
                xp = expected_points(ctx)
                eo = rank.effective_ownership(p["ownership"])
                rows.append(
                    (xp, p["web_name"], p["position"], fpl_teams.get(team_id),
                     round(mp.x_minutes), low_cov, p["ownership"],
                     rank.differential_value(xp, eo), rank.captain_rank_score(xp, eo))
                )

    rows.sort(key=lambda r: r[0], reverse=True)
    # Promoted/rebuilt squads lack the data to rank their players -> excluded, not guessed.
    reliable = [r for r in rows if not r[5]]

    print(f"\n=== xP TABLE — GW{UPCOMING_GW} {config.SEASON}  (top 20, reliable-data teams) ===")
    print(f"{'xP':>5} {'diff':>5} {'own%':>5}  {'player':<15}{'pos':<4}{'team':<16}{'~min':>4}")
    for xp, name, pos, team, mins, _low, own, diff, _cap in reliable[:20]:
        print(f"{xp:5.2f} {diff:5.2f} {own:5.1f}  {name:<15}{pos:<4}{(team or '?'):<16}{mins:>4}")

    if reliable:
        safe = reliable[0]                             # max xP (already sorted)
        # Differential captain must clear an xP floor — an unowned low-xP player is noise,
        # not a rank play (captaining 4.5 xP over 9 xP loses rank). See rank module.
        xps = [r[0] for r in reliable]
        eos = [rank.effective_ownership(r[6]) for r in reliable]
        di = rank.differential_captain_index(xps, eos, alpha=0.8)
        diffcap = reliable[di] if di is not None else None
        print(f"\n  captain — safe (max xP)      : {safe[1]} ({safe[3]}) — "
              f"{safe[0]:.2f} xP, {safe[6]:.1f}% owned")
        if diffcap is not None and diffcap[1] != safe[1]:
            print(f"  captain — differential (higher-variance, xP within 80% of best): "
                  f"{diffcap[1]} ({diffcap[3]}) — {diffcap[0]:.2f} xP, {diffcap[6]:.1f}% owned")
        else:
            print("  captain — differential       : none clears the xP floor; safe pick is the value pick too")

    low_teams = sorted(t for t, mins in coverage.items() if mins < LOW_COVERAGE)
    if low_teams:
        print(f"  excluded low-data teams: {[fpl_teams.get(t, '?') for t in low_teams]}")
    if skipped:
        print(f"  skipped {len(skipped)} fixtures (promoted/unknown to engine): {skipped}")
    print("\n  cols: xP = expected points | diff = rank-upside if owned = xP*(1-EO) | own% = ownership")
    print("  caveats: EO uses overall ownership (captain-EO needs top-manager data); near-deadline")
    print("  team news not yet ingested; new signings use prior-club output. First cut, not gospel.")


if __name__ == "__main__":
    main()
