#!/usr/bin/env python3
"""Score the news extractor against FPL's own availability field. No API key needed.

Run it weekly alongside `capture_news.py` to build a track record. In preseason the numbers are
thin and mean little; in-season they answer the question that decides whether a paid team-news
feed is worth anything: can we extract signal FPL does not already publish for free?

Usage: python scripts/eval_news.py [--json]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpledge.eval.news_eval import evaluate, fpl_labels, load_corpus
from fpledge.ingest.fpl_api import FPLClient


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    items = load_corpus()
    if not items:
        print("no captured news yet — run `make capture-news` first (docs/OPERATIONS.md)")
        raise SystemExit(1)

    res = evaluate(items, fpl_labels(FPLClient().bootstrap_static()))
    if args.json:
        print(json.dumps(res, indent=2))
        return

    print(f"corpus: {res['n_items']} unique items, {res['n_players_mentioned']} players named")
    print(f"FPL currently flags {res['n_fpl_flagged']} players\n")

    p, r, a = res["precision"], res["recall"], res["additive"]
    rate = f"{p['rate']:.0%}" if p["rate"] is not None else "n/a"
    print(f"PRECISION  feed flagged {p['flagged_by_feed']}, FPL confirms "
          f"{p['confirmed_by_fpl']} ({rate})")
    for u in p["unconfirmed"][:6]:
        print(f"             unconfirmed: {u['name']} ({u['team']})")

    rr = f"{r['rate']:.0%}" if r["rate"] is not None else "n/a"
    print(f"RECALL     FPL flags {r['fpl_flagged']}, feed mentions "
          f"{r['mentioned_by_feed']} ({rr})")
    print("             a property of the SOURCE, not the extractor — headlines and one-line")
    print("             summaries cannot see a long-term injury that stopped being news")

    print(f"\nADDITIVE   {a['count']} players with a rotation cue that FPL does NOT flag")
    for x in a["players"][:10]:
        print(f"             {x['name']} ({x['team']})")
    print("             THE ONLY CATEGORY WORTH MONEY. Injury is free from FPL; rotation is the")
    print("             whole commercial case. Treat these as candidates, not conclusions —")
    print("             the cues are deliberately over-inclusive and this is what an LLM pass")
    print("             with a verbatim-quote guard would sharpen.")

    print("\nNOTE  FPL's field is a PARTIAL oracle, not ground truth — it is itself derived from")
    print("      press conferences. A disagreement may be our error or a signal they have not")
    print("      published yet, which is why nothing here is thresholded.")


if __name__ == "__main__":
    main()
