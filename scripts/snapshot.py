#!/usr/bin/env python3
"""Capture FPL's state BEFORE a deadline. Run weekly, from 2026-08-21 onwards.

WHY THIS EXISTS, AND WHY IT IS URGENT

This project spent four months believing its model lost to FPL's own projection. It did not.
The community dataset's `xP` column is scraped *after* each gameweek and absorbs that
gameweek's points through FPL's `form` average, so it is not a forecast — controlling for prior
form, it still carries 0.430 of information about the result it is supposedly predicting, where
a genuine forecast carries 0.034. See docs/HANDOFF.md §16.

The fix is to stop depending on anyone else's scrape timing. A value captured by this script is
unambiguously pre-deadline, because it is captured before the deadline and stamped with when.

Two things become possible that are impossible today, and both are lost forever for any week
this does not run:

  A HONEST BENCHMARK. FPL's `ep_next`, recorded before the deadline it applies to. Our published
    comparison currently relies on reconstructing that by shifting a contaminated column, which
    works but understates FPL by however much they learn in the days before kickoff.

  AVAILABILITY IN THE BACKTEST. `chance_of_playing_next_round`, `status` and `news` exist only
    in the live bootstrap — no historical dataset carries them. Production already uses them to
    reduce a projection for an injured player; the backtest cannot, so every validation number
    this project has ever published describes a handicapped version of the shipped model. One
    season of snapshots makes that measurable.

Neither can be reconstructed later. The FPL API serves only the present.

WHAT IT CAPTURES
  bootstrap-static  — every player: ep_this, ep_next, form, status, chance_of_playing_*, news,
                      price, ownership, ICT components, BPS. Plus events (deadlines) and teams.
  fixtures          — kickoff times and results-to-date, which is what tells us the deadline.

Both land immutably in data/raw/ partitioned by ingest timestamp, so a re-run never overwrites
an earlier capture — the whole point is the timeline.

WHEN TO RUN IT
  Ideally 2-4 hours before each deadline, when team news has landed but the deadline has not
  passed. A cron on a machine that is awake:

      0 */6 * * *  cd /path/to/repo && .venv/bin/python scripts/snapshot.py --if-near-deadline

  `--if-near-deadline` exits without capturing unless a deadline is within `--window` hours
  (default 12), so a frequent cron produces roughly one useful snapshot per gameweek rather
  than a heap of duplicates. Run it without that flag to force a capture.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from datetime import UTC, datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpledge.ingest import capture_index, landing
from fpledge.ingest.fpl_api import FPLClient


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)   # 3.11+ parses the trailing Z
    except ValueError:
        return None


def next_deadline(events: list[dict], now: datetime) -> tuple[int | None, datetime | None]:
    """The next gameweek whose deadline has not passed."""
    upcoming = [
        (e.get("id"), _parse(e.get("deadline_time")))
        for e in events
        if _parse(e.get("deadline_time")) and _parse(e.get("deadline_time")) > now  # type: ignore[operator]
    ]
    if not upcoming:
        return None, None
    return min(upcoming, key=lambda t: t[1])  # type: ignore[arg-type,return-value]


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--if-near-deadline", action="store_true",
                    help="skip unless a deadline falls inside --window hours")
    ap.add_argument("--window", type=float, default=12.0, help="hours before a deadline (default 12)")
    args = ap.parse_args(argv)

    now = datetime.now(UTC)
    client = FPLClient()

    bootstrap = client.bootstrap_static()
    events = bootstrap.get("events", [])
    gw, deadline = next_deadline(events, now)
    hours = (deadline - now).total_seconds() / 3600 if deadline else None

    if gw is None:
        print("no upcoming deadline — season not started, or finished. Nothing to capture.")
        return
    print(f"next deadline: GW{gw} at {deadline:%Y-%m-%d %H:%M} UTC ({hours:.1f}h away)")

    if args.if_near_deadline and (hours is None or hours > args.window):
        print(f"outside the {args.window}h window — skipping (use no flag to force).")
        return

    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    paths = [
        landing.land(bootstrap, source="fpl", endpoint="bootstrap_snapshot",
                     gameweek=gw, ingest_ts=ts),
        landing.land(client.fixtures(), source="fpl", endpoint="fixtures_snapshot",
                     gameweek=gw, ingest_ts=ts),
    ]

    # A one-line-per-capture index, so "what do we have and when was it taken" never requires
    # walking the partition tree. This is the file a future backtest reads first.
    players = bootstrap.get("elements", [])
    flagged = sum(1 for p in players if (p.get("status") or "a") != "a")
    with_ep = sum(1 for p in players if float(p.get("ep_next") or 0) > 0)
    row = {
        "ingest_ts": ts,
        "captured_at": now.isoformat(),
        "for_gameweek": gw,
        "deadline": deadline.isoformat() if deadline else None,
        "hours_before_deadline": round(hours, 2) if hours is not None else None,
        "n_players": len(players),
        "n_flagged": flagged,
        "n_with_ep_next": with_ep,
        "paths": [str(p) for p in paths],
    }
    # One immutable object per capture — see the note in capture_news.py. An appended local file
    # cannot survive a scheduler, and this index is the only record that a capture happened.
    index_locator = capture_index.record(capture_index.SNAPSHOT, row, ingest_ts=ts)

    print(f"captured {len(players)} players — {with_ep} with a non-zero ep_next, "
          f"{flagged} flagged as doubtful or worse")
    print(f"indexed -> {index_locator}")
    for p in paths:
        print(f"  {p}")

    if hours is not None and hours > args.window:
        print(f"\nNOTE: taken {hours:.0f}h before the deadline. Team news lands later; a capture "
              "inside a few hours of kickoff is worth more.")


if __name__ == "__main__":
    main()
