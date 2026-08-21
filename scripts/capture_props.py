#!/usr/bin/env python3
"""Capture anytime-goalscorer prices BEFORE each deadline. Run weekly, from 2026-08-21.

WHY THIS EXISTS

The same argument as `scripts/snapshot.py`, applied to a different missing quantity, and for the
same reason: it cannot be back-filled for free.

§19 measured perfect team news at **+0.168** played-only Spearman against **+0.012** for the best
modelling change available anywhere in this project. §21 then measured our xG-fitted engine as
already matching the betting market's view of a FIXTURE — so a market feed is worth nothing for
its opinion on Arsenal vs Chelsea. It is worth having for two things it alone carries:

  THE PLAYER-LEVEL SPLIT. An anytime-goalscorer price is a market-clearing P(this player scores),
    which is exactly `goal_share x team_lambda` — the largest term in an attacker's projection,
    and the one we currently estimate from historical rates.

  TEAM NEWS, PRICED IN. A player the market expects to be benched is priced long. That buys a
    share of the +0.168 without a lineup subscription and without its 84% accuracy ceiling.

WHY FORWARD AND NOT HISTORICAL

Historical props exist from May 2023 but cost 10 credits per event, so three seasons is ~11,400
credits — about $30, or eight months of the free tier. Capturing forward costs ~10 credits a
gameweek against 500 free a month, i.e. nothing. By roughly GW10 there is enough paired data to
answer whether props beat our xP, and every week not captured is a week that then costs money.

WHAT IT CAPTURES

  events         — upcoming EPL fixtures and their ids (free, no credits)
  event odds     — anytime-goalscorer prices per fixture, every book in the region

Lands immutably under data/raw/ partitioned by ingest timestamp, and appends one line per run to
props_index.jsonl recording when it ran, for which gameweek, how long before the deadline, how
many fixtures and prices it got, and how many credits remain.

FIRST RUN — DO THIS ONCE

    python scripts/capture_props.py --list-markets

A wrong market key returns an EMPTY bookmaker list rather than an error, which is
indistinguishable from "no book has priced it yet" and would capture nothing all season while
looking like it worked. `--list-markets` asks the API which keys exist instead of trusting a
constant. Costs one event's credits.

RUNNING IT

    export ODDS_API_KEY=...      # free key: https://the-odds-api.com
    0 */6 * * *  cd /path/to/repo && .venv/bin/python scripts/capture_props.py --if-near-deadline

`--if-near-deadline` exits without spending credits unless a deadline is inside `--window` hours
(default 12). Books post goalscorer lines a day or two out, so a window much wider than that
buys prices that predate team news and defeats the purpose.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import UTC, datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpledge.ingest import capture_index, landing
from fpledge.ingest.fpl_api import FPLClient
from fpledge.ingest.oddsapi import (
    GOALSCORER_MARKET,
    NoApiKey,
    OddsApiClient,
    OddsApiError,
    goalscorer_prices,
)


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def next_deadline(events: list[dict], now: datetime):
    """The soonest deadline still ahead of `now`, as (gameweek, deadline).

    Shared shape with snapshot.py deliberately: a props capture filed against the wrong
    gameweek is worse than a missing one, because it looks like evidence.
    """
    best_gw, best_dt = None, None
    for e in events or []:
        dt = _parse(e.get("deadline_time"))
        if dt is None or dt <= now:
            continue
        if best_dt is None or dt < best_dt:
            best_gw, best_dt = e.get("id"), dt
    return best_gw, best_dt


def gameweek_fixtures(events: list[dict], deadline, following) -> list[dict]:
    """The odds-API fixtures that belong to THIS gameweek: kickoff after its deadline, at or
    before the next gameweek's. Module-level and pure because the inverted version of this
    filter (kickoff <= deadline, with a confident comment) shipped and captured zero prices —
    logic that has already been wrong once does not get to live inline and untested."""
    if deadline is None:
        return list(events)
    out = []
    for e in events:
        ko = _parse(e.get("commence_time"))
        if ko is not None and ko > deadline and (following is None or ko <= following):
            out.append(e)
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--if-near-deadline", action="store_true",
                    help="capture only when a deadline is inside --window hours")
    ap.add_argument("--window", type=float, default=12.0)
    ap.add_argument("--market", default=GOALSCORER_MARKET)
    ap.add_argument("--regions", default="uk")
    ap.add_argument("--list-markets", action="store_true",
                    help="ask the API which market keys exist for the next fixture, then exit")
    args = ap.parse_args(argv)

    now = datetime.now(UTC)
    boot = FPLClient().bootstrap_static()
    gw, deadline = next_deadline(boot.get("events", []), now)
    hours = (deadline - now).total_seconds() / 3600 if deadline else None

    if gw is None:
        print("no upcoming deadline — season not started, or finished. Nothing to capture.")
        return
    print(f"next deadline: GW{gw} at {deadline:%Y-%m-%d %H:%M} UTC ({hours:.1f}h away)")

    # The window check comes BEFORE the odds API is touched. A six-hourly cron fires ~28 times
    # a gameweek and should do nothing on ~27 of them; reaching the network first would spend a
    # request each time to learn what the FPL deadline already told us.
    if not args.list_markets and args.if_near_deadline and (hours is None or hours > args.window):
        print(f"outside the {args.window}h window — skipping, nothing requested.")
        return

    try:
        client = OddsApiClient()
        events = client.events()
    except NoApiKey as exc:
        print(f"NOT CAPTURED: {exc}")
        raise SystemExit(2) from exc
    except OddsApiError as exc:
        print(f"NOT CAPTURED: {exc}")
        raise SystemExit(1) from exc

    if args.list_markets:
        if not events:
            print("no upcoming events listed by the odds API.")
            return
        ev = events[0]
        print(f"markets offered for {ev.get('home_team')} v {ev.get('away_team')}:")
        print(json.dumps(client.list_markets(ev["id"], regions=args.regions), indent=1)[:4000])
        return

    # A gameweek's fixtures kick off AFTER its deadline — the deadline is the last moment to set
    # a team before those matches — and run until the NEXT gameweek's deadline. The first version
    # had this filter INVERTED (kickoff <= deadline), complete with a confident comment
    # rationalising the wrong direction, and it captured zero prices while exiting 0. It was
    # caught only because the runbook insists a never-run capture is proven by hand before being
    # scheduled: on a scheduler it would have burned credits reporting success all season.
    following = min((d for e in boot.get("events", [])
                     if (d := _parse(e.get("deadline_time"))) and deadline and d > deadline),
                    default=None)
    upcoming = gameweek_fixtures(events, deadline, following)
    print(f"{len(upcoming)} of {len(events)} listed fixtures are GW{gw}'s "
          f"(kickoff after its deadline, before the next)")

    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    payloads, prices, failed = [], [], []
    for ev in upcoming:
        try:
            payload = client.event_odds(ev["id"], markets=args.market, regions=args.regions)
        except OddsApiError as exc:
            failed.append({"event": ev.get("id"), "error": str(exc)})
            continue
        payloads.append(payload)
        prices.extend(goalscorer_prices(payload))

    path = landing.land({"captured_at": now.isoformat(), "for_gameweek": gw,
                         "market": args.market, "regions": args.regions,
                         "events": payloads},
                        source="oddsapi", endpoint="goalscorer_props",
                        gameweek=gw, ingest_ts=ts)

    priced_events = sum(1 for p in payloads if p.get("bookmakers"))
    row = {
        "ingest_ts": ts,
        "captured_at": now.isoformat(),
        "for_gameweek": gw,
        "deadline": deadline.isoformat() if deadline else None,
        "hours_before_deadline": round(hours, 2) if hours is not None else None,
        "market": args.market,
        "regions": args.regions,
        "n_events": len(payloads),
        "n_events_with_prices": priced_events,
        "n_prices": len(prices),
        "n_players": len({p["player"] for p in prices if p.get("player")}),
        "credits_used": client.credits_used,
        "credits_remaining": client.credits_remaining,
        "failed": failed,
        "path": str(path),
    }
    # One immutable object per capture, wherever the raw zone points — the same migration the
    # other captures made. An appended local file cannot survive a scheduler, and this index is
    # the only record that credits were spent on a capture at all.
    index_locator = capture_index.record(capture_index.PROPS, row, ingest_ts=ts)

    print(f"captured {len(prices)} prices for {row['n_players']} players "
          f"across {priced_events}/{len(payloads)} fixtures")
    print(f"credits: used {client.credits_used}, remaining {client.credits_remaining}")
    if failed:
        print(f"WARNING: {len(failed)} fixtures failed — see the index row")
    if priced_events == 0 and payloads:
        # The failure this whole script is most likely to suffer, and the one that looks fine.
        print("WARNING: every fixture came back with NO bookmakers. Either no book has priced "
              f"'{args.market}' yet, or the market key is wrong. Run --list-markets to tell "
              "the difference — a wrong key captures nothing all season and looks like a quiet "
              "week every time.")
        raise SystemExit(1)
    if not upcoming:
        # Inside the capture window there is always a gameweek of fixtures ahead; finding none
        # means the filter or the listing is broken, not that the week is quiet. Exit non-zero
        # AFTER landing and indexing, so the evidence of what the API returned is preserved —
        # this is the state the inverted filter produced, and it must never again read as
        # success on a machine nobody is watching.
        print("ERROR: no fixtures matched this gameweek inside the capture window")
        raise SystemExit(1)
    print(f"indexed -> {index_locator}")
    print(f"  {path}")


if __name__ == "__main__":
    main()
