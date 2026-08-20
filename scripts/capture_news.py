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
import pathlib
import sys
from datetime import UTC, datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpledge.api import store
from fpledge.eval.news_eval import build_digest, fpl_labels, load_corpus
from fpledge.ingest import capture_index, landing
from fpledge.ingest.fpl_api import FPLClient
from fpledge.ingest.newsfeed import (
    NewsFeedClient,
    NewsFeedError,
    clubs_in_play,
    coverage,
    cue_tags,
    mentions,
)


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

    # The league comes from the BOOTSTRAP, never from a hardcoded list. Composition changes every
    # season: the first version of this shipped with three relegated clubs and without three
    # promoted ones, so three clubs contributed no team news at all while the run reported
    # "20/20 clubs" — it was counting its own wrong list.
    in_league, no_feed = clubs_in_play(boot)
    if no_feed:
        # Loud, and non-zero. A club no source covers is silent for a whole season and every
        # other signal looks healthy, so this must never be a warning you can scroll past.
        print(f"ERROR: {len(no_feed)} club(s) in the league have no feed on ANY source: "
              f"{', '.join(no_feed)}")
        print("Add them in fpledge/ingest/newsfeed.py before capturing again (run")
        print("scripts/probe_news_feeds.py to find working slugs) — until then they contribute")
        print("NO team news at all and nothing else would say so.")
        raise SystemExit(1)

    client = NewsFeedClient()
    clubs = args.clubs or in_league
    print(f"{len(in_league)} clubs in the league this season, all covered by at least one source")

    # Per-source reach, printed every run. Sources are additive and none of them covers everyone
    # — the Guardian has no Brighton tag, eleven clubs publish no feed of their own — so "how
    # thin is each publisher today" is a number worth watching rather than assuming.
    for name, covered in coverage(clubs).items():
        gaps = [c for c in clubs if c not in covered]
        note = f"  (no feed: {', '.join(gaps)})" if gaps else ""
        print(f"  {name:<9} covers {len(covered)}/{len(clubs)} clubs{note}")

    items, failed, partial = [], [], []
    for club in clubs:
        try:
            # Partial failures land in `partial` and cost coverage; only a club whose every
            # source failed raises and lands in `failed`.
            got = client.club(club, failures=partial)
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
    by_source: dict[str, int] = {}
    chars_by_source: dict[str, int] = {}
    for it in items:
        by_source[it["source"]] = by_source.get(it["source"], 0) + 1
        chars_by_source[it["source"]] = chars_by_source.get(it["source"], 0) + len(it["summary"])
    row = {
        "ingest_ts": ts,
        "captured_at": now.isoformat(),
        "clubs_requested": len(clubs),
        "clubs_ok": len(clubs) - len(failed),
        "n_items": len(items),
        "n_items_naming_a_player": len(with_mentions),
        "n_items_with_cues": len(with_cues),
        "items_by_source": by_source,
        # Mean summary length per source. The whole reason for more than one source is that this
        # number varies ~20x between publishers, and it is what decides whether an item is
        # extractable prose or just a headline. Tracking it makes a feed going thin visible.
        "mean_summary_chars_by_source": {
            k: round(chars_by_source[k] / v) for k, v in by_source.items() if v
        },
        "failed": failed,
        "partial": partial,
        "path": str(path),
    }
    # One immutable object per capture, wherever the raw zone is configured — NOT an append to a
    # local file. A Lambda's filesystem is read-only apart from /tmp and /tmp dies with the
    # execution environment, so an appended index would lose the only record that this capture
    # ran while its data sat in the raw zone, invisible to every reader.
    index_locator = capture_index.record(capture_index.NEWS, row, ingest_ts=ts)

    # Serving digest, written by the CAPTURE rather than the weekly precompute: news is daily,
    # and folding it into the gameweek artifact would make it up to seven days stale on a page
    # whose whole value is being current. The API stays a pure reader either way.
    corpus = load_corpus() or items
    digest = build_digest(corpus, fpl_labels(boot), now.isoformat(), clubs_allowed=in_league)
    # Through the serving store rather than straight to a path, so the digest follows
    # FPLEDGE_SERVING_URI wherever it points. A capture on a scheduler writing to a local
    # filesystem would produce a digest that is discarded seconds later, and the page it feeds
    # would simply never update — with the capture reporting success every time.
    digest_locator = store.write_artifact("news.json", digest)

    print(f"captured {len(items)} items from {row['clubs_ok']}/{len(clubs)} clubs — "
          f"{len(with_mentions)} name a player, {len(with_cues)} carry an intent cue")
    for name in sorted(by_source):
        print(f"  {name:<9} {by_source[name]:>4} items, "
              f"mean summary {row['mean_summary_chars_by_source'][name]:>5} chars")
    print(f"digest -> {digest_locator} "
          f"({digest['n_clubs']} clubs, {digest['n_items']} items in corpus)")
    for it in with_mentions[:8]:
        who = ", ".join(m["name"] for m in it["mentions"])
        print(f"  [{it['club']}/{it['source']}] {it['title'][:60]}")
        print(f"      -> {who}   cues={it['cues'] or '-'}")
    if partial:
        # Not fatal — the club still has its other sources — but a source that quietly stops
        # working is how a corpus gets thinner every week without anyone noticing.
        print(f"NOTE: {len(partial)} source(s) failed without costing a club its coverage:")
        for p in partial[:10]:
            print(f"  - {p['error']}")
    if failed:
        # Every source for this club failed. It has no team news at all and nothing else says so.
        print(f"WARNING: {len(failed)} club(s) lost EVERY source: "
              f"{', '.join(f['club'] for f in failed)}")
    print(f"indexed -> {index_locator}")
    if row["clubs_ok"] == 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
