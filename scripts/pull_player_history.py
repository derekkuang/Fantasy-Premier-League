#!/usr/bin/env python3
"""Pull each player's PAST-SEASON aggregates (xG/xA/minutes/goals/assists) from the FPL API.

element-summary's `history_past` gives prior-season totals keyed by the stable FPL code —
last season's xG/xA per player with NO scraping and NO external id map. This is the
goal/assist-share base for the first expected-points table. ~558 throttled calls.

Usage: python scripts/pull_player_history.py
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpledge import config
from fpledge.ingest import landing
from fpledge.ingest.fpl_api import FPLClient
from fpledge.storage import duck
from fpledge.storage import load as storeload

LAST_SEASON = "2025/26"  # most recent completed season (history_past season_name form)


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def main() -> None:
    client = FPLClient(min_interval=0.25)
    boot = client.bootstrap_static()
    elements = boot["elements"]
    print(f"pulling history_past for {len(elements)} players (throttled ~0.25s)...")

    records = []
    for i, e in enumerate(elements):
        try:
            summary = client.element_summary(e["id"])
        except Exception as ex:  # noqa: BLE001
            print(f"  warn: element {e['id']} failed: {ex}")
            continue
        past = {p["season_name"]: p for p in summary.get("history_past", [])}
        last = past.get(LAST_SEASON)
        records.append(
            {
                "code": e["code"],
                "element_id": e["id"],
                "web_name": e["web_name"],
                "team_id": e["team"],
                "position": config.ELEMENT_TYPE_TO_POS[e["element_type"]],
                "minutes": (last or {}).get("minutes", 0),
                "goals": (last or {}).get("goals_scored", 0),
                "assists": (last or {}).get("assists", 0),
                "starts": (last or {}).get("starts", 0),
                "xg": _f((last or {}).get("expected_goals")),
                "xa": _f((last or {}).get("expected_assists")),
                "ownership": _f(e.get("selected_by_percent")),
                "ep_next": _f(e.get("ep_next")),
                "dc": (last or {}).get("defensive_contribution", 0) or 0,
                "bonus": (last or {}).get("bonus", 0) or 0,
            }
        )
        if (i + 1) % 100 == 0:
            print(f"  {i + 1}/{len(elements)}")

    landing.land(records, source="fpl_api", endpoint="player_history")
    con = duck.connect()
    con.execute("DROP TABLE IF EXISTS player_season")  # recreate with the extended columns
    duck.init_schema(con)
    n = storeload.load_player_season(con, records)
    with_xg = con.execute("SELECT count(*) FROM player_season WHERE season=? AND xg>0", [config.SEASON]).fetchone()[0]
    con.close()
    print(f"landed + loaded {n} player-season rows ({with_xg} with last-season xG)")


if __name__ == "__main__":
    main()
