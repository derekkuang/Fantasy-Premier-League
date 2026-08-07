#!/usr/bin/env python3
"""Capture club news feeds daily. The raw material for team-news extraction.

WHY, in one line: §19 measured perfect team news at +0.168 played-only Spearman against +0.012
for the best modelling change in this project, and rotation — the half FPL's own availability
field does not encode — originates in press conferences.

WHY DAILY RATHER THAN AT THE DEADLINE. Unlike `snapshot.py` and `capture_props.py`, which want
one reading as close to the deadline as possible, feeds are a ROLLING WINDOW. BBC's per-club
feeds carry roughly the last 4-24 items and older ones fall off permanently. A weekly capture
would miss the Tuesday presser entirely. Run it daily, or more often; it is free and the items
dedupe by guid.

    0 7,13,19 * * *  cd /path/to/repo && .venv/bin/python scripts/capture_news.py

WHAT IT DOES NOT DO. It reads RSS and never fetches an article body. That is a deliberate
posture — a feed is published for machine consumption — and it caps what is available: an item
gives a headline and a one-line summary, not the paragraph where a manager says who is fit. So
this captures a corpus and does a deterministic first pass over it; it does not conclude
anything about any player. See the extraction plan in docs/HANDOFF.md.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import UTC, datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpledge import config
from fpledge.ingest import landing
from fpledge.ingest.fpl_api import FPLClient
from fpledge.ingest.newsfeed import (
    BBC_SLUGS,
    NewsFeedClient,
    NewsFeedError,
    cue_tags,
    mentions,
)

INDEX = config.DATA_DIR / "raw" / "news_index.jsonl"


def fpl_players(bootstrap: dict) -> list[dict]:
    """The current player list, shaped for `mentions`."""
    teams = {t["id"]: t["name"] for t in bootstrap.get("teams", [])}
    out = []
    for e in bootstrap.get("elements", []):
        first, second = e.get("first_name", ""), e.get("second_name", "")
        out.append({
            "element_id": e["id"],
            "web_name": e.get("web_name"),
            "full_name": f"{first} {second}".strip(),
            "team": teams.get(e.get("team")),
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clubs", nargs="*", default=None, help="default: all 20")
    args = ap.parse_args()

    now = datetime.now(UTC)
    ts = now.strftime("%Y%m%dT%H%M%SZ")

    boot = FPLClient().bootstrap_static()
    players = fpl_players(boot)
    print(f"{len(players)} FPL players loaded for name matching")

    client = NewsFeedClient()
    clubs = args.clubs or list(BBC_SLUGS)
    items, failed = [], []
    for club in clubs:
        try:
            got = client.club(club)
        except NewsFeedError as exc:
            failed.append({"club": club, "error": str(exc)})
            continue
        for it in got:
            it["mentions"] = mentions(it, players)
            it["cues"] = cue_tags(it)
        items.extend(got)

    path = landing.land({"captured_at": now.isoformat(), "items": items},
                        source="newsfeed", endpoint="club_rss", ingest_ts=ts)

    with_mentions = [i for i in items if i["mentions"]]
    with_cues = [i for i in items if i["cues"]]
    row = {
        "ingest_ts": ts,
        "captured_at": now.isoformat(),
        "clubs_requested": len(clubs),
        "clubs_ok": len(clubs) - len(failed),
        "n_items": len(items),
        "n_items_naming_a_player": len(with_mentions),
        "n_items_with_cues": len(with_cues),
        "failed": failed,
        "path": str(path),
    }
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    with INDEX.open("a") as fh:
        fh.write(json.dumps(row) + "\n")

    print(f"captured {len(items)} items from {row['clubs_ok']}/{len(clubs)} clubs — "
          f"{len(with_mentions)} name a player, {len(with_cues)} carry an intent cue")
    for it in with_mentions[:8]:
        who = ", ".join(m["name"] for m in it["mentions"])
        print(f"  [{it['club']}] {it['title'][:60]}")
        print(f"      -> {who}   cues={it['cues'] or '-'}")
    if failed:
        # A club that 404s has no team news all season and nothing else would say so.
        print(f"WARNING: {len(failed)} club feeds failed: "
              f"{', '.join(f['club'] for f in failed)}")
    print(f"indexed -> {INDEX}")
    if row["clubs_ok"] == 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
