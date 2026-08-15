#!/usr/bin/env python3
"""Verify every configured news feed, and probe candidates for clubs that have none.

WHY THIS IS A SCRIPT AND NOT A RESEARCH SESSION. The feed tables in `fpledge/ingest/newsfeed.py`
are hardcoded, and this project has already been bitten once by a hardcoded league-shaped
constant: three relegated clubs sat in the slug table while three promoted ones were missing, so
three clubs contributed no team news all season and the run reported "20/20 clubs" because it was
counting its own wrong list. Publishers rename tags, drop RSS, and put clubs behind bot
protection. Re-verification has to be one command or it will not happen.

Run it after promotion/relegation, when a capture starts reporting failures, or from a different
network when a result looks like blocking rather than absence:

    python scripts/probe_news_feeds.py                # verify what is configured
    python scripts/probe_news_feeds.py --candidates   # also hunt slugs for uncovered clubs

WHAT COUNTS AS WORKING. Three things, because any one of them alone lies:
  - HTTP 200                  a 404 is the honest failure and the easy one
  - parses, with >0 items     a 200 serving an HTML error page is not a feed
  - announces the right title an unrecognised Guardian slug returns HTTP 200 and twenty valid
                              items from the SITE-WIDE football feed. It looks healthier than a
                              real quiet club because it has more items, and only the channel
                              title can tell them apart.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import requests

from fpledge import config
from fpledge.ingest.fpl_api import FPLClient
from fpledge.ingest.newsfeed import (
    GUARDIAN_TEAM_FEED,
    KIND_PL,
    KIND_RSS,
    SOURCES,
    NewsFeedError,
    _norm_title,
    clubs_in_play,
    parse_feed,
    parse_pl_content,
)

# Tried against clubs no source covers. Guardian tag naming is genuinely inconsistent
# (`manchestercity` but `manchester-united`), so the shapes below are all guesses by pattern.
GUARDIAN_SHAPES = (
    "{a}", "{a}united", "{a}-united", "{a}city", "{a}-city", "{a}town", "{a}fc",
)


def check(url: str, expect: str | None, timeout: int, *,
          kind: str = KIND_RSS, slug: str | None = None) -> tuple[bool, str]:
    """(ok, human-readable verdict)."""
    try:
        resp = requests.get(url, headers={"User-Agent": config.HTTP_USER_AGENT}, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 — any transport failure is just "unreachable"
        return False, f"{type(exc).__name__}"
    if resp.status_code != 200:
        note = "  (edge blocking? retry off VPN)" if resp.status_code in (403, 429) else ""
        return False, f"HTTP {resp.status_code}{note}"

    if kind == KIND_PL:
        # The tag filter fails open — an unknown tag returns other clubs' items under a 200 — so
        # "did anything come back" is not the question. "Did anything come back for THIS club" is.
        try:
            items = parse_pl_content(resp.text, slug or "")
        except NewsFeedError as exc:
            return False, str(exc)[:96]
        if not items:
            return False, "no items tagged for this club"
        mean_len = statistics.mean(len(i["summary"]) for i in items)
        return True, f"{len(items):>3} items, mean summary {mean_len:>5.0f} chars, tag {slug!r}"

    try:
        title, items = parse_feed(resp.text)
    except Exception as exc:  # noqa: BLE001
        return False, f"unparseable: {str(exc)[:60]}"
    if not items:
        return False, "200 but zero items (probably an HTML page)"
    mean_len = statistics.mean(len(i["summary"]) for i in items)
    if expect is not None and _norm_title(title) != _norm_title(expect):
        return False, f"WRONG FEED: announces {title!r}, expected {expect!r}"
    return True, f"{len(items):>3} items, mean summary {mean_len:>5.0f} chars, {title!r}"


def verify(clubs: list[str], timeout: int) -> list[str]:
    jobs = [(s, c) for s in SOURCES for c in clubs if c in s.feeds]
    print(f"verifying {len(jobs)} configured feeds across {len(SOURCES)} sources\n")
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(
            lambda j: check(j[0].url(j[1]), j[0].expected_title(j[1]), timeout,
                            kind=j[0].kind, slug=j[0].feeds[j[1]]),
            jobs))

    for (source, club), (ok, note) in zip(jobs, results):
        print(f"{'ok  ' if ok else 'FAIL'} {club:<15} {source.name:<9} {note}")

    print()
    covered = {c for (s, c), (ok, _) in zip(jobs, results) if ok}
    orphans = [c for c in clubs if c not in covered]
    for source in SOURCES:
        n = sum(1 for (s, _), (ok, _) in zip(jobs, results) if s is source and ok)
        print(f"  {source.name:<9} {n}/{len(clubs)} clubs working")
    if orphans:
        print(f"\nNO WORKING SOURCE AT ALL: {', '.join(orphans)}")
        print("These clubs contribute no team news. Fix before the next capture.")
    else:
        print(f"\nall {len(clubs)} clubs have at least one working source")
    return orphans


def candidates(clubs: list[str], timeout: int) -> None:
    """Hunt Guardian slugs for clubs nothing covers. Cheap, and it beats guessing by hand."""
    uncovered = [c for c in clubs if not any(c in s.feeds for s in SOURCES)]
    if not uncovered:
        print("\nevery club is configured; no candidates to hunt")
        return
    print(f"\nhunting Guardian slugs for {len(uncovered)} uncovered club(s)")
    jobs = []
    for club in uncovered:
        base = club.lower().replace("'", "").replace(" ", "")
        for shape in GUARDIAN_SHAPES:
            jobs.append((club, shape.format(a=base)))
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(
            lambda j: check(GUARDIAN_TEAM_FEED.format(slug=j[1]), None, timeout), jobs))
    for (club, slug), (ok, note) in zip(jobs, results):
        # A hit here still needs its title checked by eye before being pasted into the table:
        # the site-wide football feed answers 200 for slugs that do not exist.
        if ok:
            print(f"  candidate {club:<15} {slug:<24} {note}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", action="store_true",
                    help="hunt slugs for clubs no source covers")
    ap.add_argument("--timeout", type=int, default=config.HTTP_TIMEOUT)
    ap.add_argument("--clubs", nargs="*", default=None, help="default: this season's league")
    args = ap.parse_args()

    if args.clubs:
        clubs = args.clubs
    else:
        known, unknown = clubs_in_play(FPLClient().bootstrap_static())
        clubs = sorted(known + unknown)   # probe the uncovered ones too; that is the point
        print(f"league from the FPL bootstrap: {len(clubs)} clubs\n")

    orphans = verify(clubs, args.timeout)
    if args.candidates:
        candidates(clubs, args.timeout)
    # Non-zero ONLY when a club has no working source at all. A single dead source is expected
    # and survivable — BBC's feeds in particular time out under concurrency — and failing the
    # command on that would train you to ignore its exit code, which is the one thing it must
    # never do given what it is guarding.
    raise SystemExit(1 if orphans else 0)


if __name__ == "__main__":
    main()
