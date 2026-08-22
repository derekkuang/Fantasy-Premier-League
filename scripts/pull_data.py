#!/usr/bin/env python3
"""Pull core FPL data and land it, immutable + timestamped, in data/raw/.

Usage:
    python scripts/pull_data.py            # bootstrap-static + fixtures + finalised event-lives

Alongside the bootstrap and fixtures, this lands `event/{gw}/live/` once per FINALISED
gameweek — the per-player minutes evidence the recency minutes model reads. One object per
gameweek, landed when FPL marks it `data_checked` (points final, no further revisions) and
never re-landed: presence in the raw zone is the idempotency check, so the daily schedule
costs one extra API call per completed gameweek, once, ever.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpledge.ingest import landing
from fpledge.ingest.fpl_api import FPLClient


def main() -> None:
    client = FPLClient()

    boot = client.bootstrap_static()
    fp1 = landing.land(boot, source="fpl_api", endpoint="bootstrap")
    print(f"landed bootstrap-static -> {fp1}")

    fixtures = client.fixtures()
    fp2 = landing.land(fixtures, source="fpl_api", endpoint="fixtures")
    print(f"landed fixtures        -> {fp2}")

    # One listing answers "which gameweeks are already landed" for the whole loop — not one
    # probe per gameweek, which by late season is 37 pointless LIST round trips per daily run.
    already = {
        landing.gameweek_of(loc)
        for loc in landing.list_partitions("fpl_api", "event_live")
    }
    n_live, live_failed = 0, []
    for e in boot.get("events", []):
        gw = e.get("id")
        if gw is None or not e.get("data_checked") or gw in already:
            continue
        # Per-gameweek containment: on a cold backfill this loop is the run's longest leg,
        # and one failed gameweek must cost one gameweek — not every one after it. A miss is
        # recoverable (event-live is historical and re-fetchable), so failures warn and the
        # next scheduled run picks them up.
        try:
            live = client.event_live(gw)
        except Exception as exc:  # noqa: BLE001 — contain, report, continue
            live_failed.append(gw)
            print(f"warn: event/{gw}/live failed ({type(exc).__name__}: {exc}) — "
                  "will retry next run")
            continue
        fp = landing.land(live, source="fpl_api", endpoint="event_live", gameweek=gw)
        n_live += 1
        print(f"landed event/{gw}/live  -> {fp}")

    n_players = len(boot.get("elements", []))
    n_teams = len(boot.get("teams", []))
    print(f"ok: landed {n_teams} teams, {n_players} players, {len(fixtures)} fixtures, "
          f"{n_live} new event-live gameweek(s)"
          + (f", {len(live_failed)} FAILED ({live_failed})" if live_failed else ""))


if __name__ == "__main__":
    main()
