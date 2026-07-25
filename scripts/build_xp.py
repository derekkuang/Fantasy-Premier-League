#!/usr/bin/env python3
"""Build the first expected-points (xP) table for the upcoming gameweek.

Pipeline: fit Dixon-Coles on historical results -> map FPL team names to the engine's
Football-Data names -> distribute each fixture's team goal expectation to players via a
minutes-aware per-90 attribution (`match_shares`) -> apply the minutes model -> rank by xP.

Honest caveats (printed): promoted teams have no engine history (fixtures skipped);
low-data squads (promoted/rebuilt) have unreliable shares and are flagged with '*';
defensive-contribution points need per-match data (not yet ingested, treated as 0);
new signings carry their previous club's output as a prior.

Usage: python scripts/build_xp.py
"""

from __future__ import annotations

import pathlib
import sys
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpledge import config  # noqa: E402
from fpledge.ingest import footballdata  # noqa: E402
from fpledge.models.dixon_coles import DixonColesModel  # noqa: E402
from fpledge.models.minutes import MinutesModel  # noqa: E402
from fpledge.models.shares import match_shares, team_minutes  # noqa: E402
from fpledge.models.teammap import build_team_map  # noqa: E402
from fpledge.models.xpoints import PlayerContext, expected_points  # noqa: E402
from fpledge.storage import duck  # noqa: E402

SEASONS = ["2324", "2425", "2526"]
UPCOMING_GW = 1
LOW_COVERAGE = 9000  # current-squad last-season minutes below this -> shares unreliable
PLAYER_COLS = ["code", "team_id", "position", "web_name", "minutes", "starts", "xg", "xa"]


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
                sh = shares.get(p["code"], {"goal_share": 0.0, "assist_share": 0.0})
                mp = minutes_pred[p["code"]]
                ctx = PlayerContext(
                    position=p["position"],
                    p_play=mp.p_play,
                    p_60=mp.p_60,
                    team_lambda=team_lambda,
                    goal_share=sh["goal_share"],
                    assist_share=sh["assist_share"],
                    p_clean_sheet=p_cs,
                    x_saves=(opp_lambda * 3.0 * (mp.x_minutes / 90.0) if p["position"] == "GK" else 0.0),
                    p_dc_point=0.0,  # needs per-match defensive-action data (Phase 2)
                )
                rows.append(
                    (expected_points(ctx), p["web_name"], p["position"],
                     fpl_teams.get(team_id), round(mp.x_minutes), low_cov)
                )

    rows.sort(key=lambda r: r[0], reverse=True)
    # Promoted/rebuilt squads lack the last-season data to rank their players — we simply
    # don't have the evidence, so they are excluded from the table rather than guessed.
    reliable = [r for r in rows if not r[5]]
    print(f"\n=== xP TABLE — GW{UPCOMING_GW} {config.SEASON}  (top 20, reliable-data teams) ===")
    print(f"{'xP':>5}  {'player':<16}{'pos':<5}{'team':<18}{'~min':>4}")
    for xp, name, pos, team, mins, _low in reliable[:20]:
        print(f"{xp:5.2f}  {name:<16}{pos:<5}{(team or '?'):<18}{mins:>4}")

    if reliable:
        print(f"\n  captain pick: {reliable[0][1]} ({reliable[0][3]}) — {reliable[0][0]:.2f} xP")
    low_teams = sorted(t for t, mins in coverage.items() if mins < LOW_COVERAGE)
    if low_teams:
        names = [fpl_teams.get(t, "?") for t in low_teams]
        print(f"  * low last-season-data teams (shares unreliable): {names}")
    if skipped:
        print(f"  skipped {len(skipped)} fixtures (promoted/unknown to engine): {skipped}")
    print("\n  caveats: DC points = 0 (needs defensive-action data), new signings use prior-club")
    print("  output, GK saves are a rough opponent-lambda proxy. First cut, not gospel.")


if __name__ == "__main__":
    main()
