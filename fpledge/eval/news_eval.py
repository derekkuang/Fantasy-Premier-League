"""Score the news extractor against FPL's own availability field.

WHY THIS CAN RUN TODAY, when the rest of the team-news question cannot.

There are two separate questions and they were being conflated:

  HOW BIG IS THE PRIZE?  How much of §19's +0.168 does FPL's free `chance_of_playing_next_round`
                         already capture, leaving the rotation half as the only thing a paid feed
                         could sell? That needs the snapshot series starting 2026-08-21 and
                         cannot be answered before then.

  CAN OUR FEED CLAIM IT? Does anything we extract from free RSS actually correspond to reality?
                         That needs **no new data at all**, because FPL's own `status` and `news`
                         fields are a labelled validation set that exists right now.

The second was available from the beginning and treating it as blocked on the first was a
sequencing error. This module answers it, on whatever corpus has been captured so far.

WHAT THE THREE NUMBERS MEAN, and which one matters:

  precision — of the players we flag as injured/suspended, how many does FPL confirm? A false
              positive is the dangerous direction: acting on "X is out" when he is fit is worse
              than knowing nothing, because the projection acts on it.
  recall    — of the players FPL flags, how many does the feed mention at all? This is the
              ceiling on what a headline-and-summary corpus can ever see, and it is a property
              of the SOURCE rather than of the extractor.
  additive  — players discussed with a ROTATION cue that FPL does not flag. **This is the only
              category worth money.** Injury we already get free; rotation is the entire
              commercial case for a paid feed, and the entire reason to extract at all.

Precision and recall are scored against a partial oracle: FPL's field is itself derived from
press conferences and is not ground truth. A disagreement is not automatically our error — it
may be a genuine signal FPL has not published yet. Which is why they are reported, never
thresholded.
"""

from __future__ import annotations

import gzip
import json
import pathlib
from collections import defaultdict

from .. import config


def load_corpus(index_path: pathlib.Path | None = None) -> list[dict]:
    """Every captured item, deduped by guid. Captures overlap by design."""
    idx = index_path or (config.DATA_DIR / "raw" / "news_index.jsonl")
    if not idx.exists():
        return []
    items: list[dict] = []
    for line in idx.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        path = pathlib.Path(json.loads(line).get("path", ""))
        if not path.exists():
            continue
        with gzip.open(path, "rt") as fh:
            items.extend(json.load(fh).get("items", []))
    seen, uniq = set(), []
    for it in items:
        key = it.get("guid") or it.get("link")
        if key and key not in seen:
            seen.add(key)
            uniq.append(it)
    return uniq


def fpl_labels(bootstrap: dict) -> dict:
    """{element_id: {...}} with FPL's own view. `flagged` is the label we score against."""
    teams = {t["id"]: t["name"] for t in bootstrap.get("teams", [])}
    out = {}
    for e in bootstrap.get("elements", []):
        news = (e.get("news") or "").strip()
        status = e.get("status") or "a"
        out[e["id"]] = {
            "name": e.get("web_name"),
            "team": teams.get(e.get("team")),
            "status": status,
            "news": news,
            "flagged": status != "a" or bool(news),
        }
    return out


def evaluate(items: list[dict], labels: dict) -> dict:
    """Precision, recall and the additive set. Counts only — no thresholds, no verdict."""
    cues_by_player: dict = defaultdict(set)
    for it in items:
        for m in it.get("mentions", []):
            cues_by_player[m["element_id"]].update(it.get("cues", []))

    flagged = {i for i, p in labels.items() if p["flagged"]}
    feed_injury = {e for e, c in cues_by_player.items() if {"injury", "suspension"} & c}
    feed_rotation = {e for e, c in cues_by_player.items() if "rotation" in c}

    confirmed = feed_injury & flagged
    mentioned_and_flagged = flagged & set(cues_by_player)
    additive = feed_rotation - flagged

    def named(ids):
        return sorted(
            ({"element_id": e, **{k: labels[e][k] for k in ("name", "team", "news")}}
             for e in ids if e in labels),
            key=lambda r: (r["team"] or "", r["name"] or ""),
        )

    return {
        "n_items": len(items),
        "n_players_mentioned": len(cues_by_player),
        "n_fpl_flagged": len(flagged),
        "precision": {
            "flagged_by_feed": len(feed_injury),
            "confirmed_by_fpl": len(confirmed),
            "rate": round(len(confirmed) / len(feed_injury), 3) if feed_injury else None,
            "unconfirmed": named(feed_injury - flagged),
        },
        "recall": {
            "fpl_flagged": len(flagged),
            "mentioned_by_feed": len(mentioned_and_flagged),
            "rate": round(len(mentioned_and_flagged) / len(flagged), 3) if flagged else None,
        },
        "additive": {
            "count": len(additive),
            "players": named(additive),
        },
    }


# --- the serving digest ------------------------------------------------------------------- #
# Written by `capture_news.py` so the API stays a pure reader, and written by the CAPTURE rather
# than the weekly precompute because news is daily — folding it into the gameweek artifact would
# make it up to seven days stale on a page whose entire value is being current.
DIGEST_ITEM_CAP = 6          # per club, newest first


def build_digest(items: list[dict], labels: dict, generated_at: str,
                 clubs_allowed: list[str] | None = None) -> dict:
    """A club-keyed digest for the beta page.

    Carries FPL's own status alongside every mention, so the page can show what FPL says next to
    what a feed said. That pairing IS the honesty: where they agree we have added nothing, and
    where they differ the reader can see both rather than being told which to believe.

    `clubs_allowed` is the CURRENT league, from the bootstrap. The corpus is cumulative and
    outlives a season, so without it a relegated club keeps appearing on the page months after
    it left the division — which is how the page came to report 23 clubs in a 20-team league.
    """
    allowed = set(clubs_allowed) if clubs_allowed else None
    by_club: dict = {}
    for it in items:
        club = it.get("club") or "?"
        if allowed is not None and club not in allowed:
            continue
        by_club.setdefault(club, []).append(it)

    clubs = {}
    for club, rows in by_club.items():
        rows = sorted(rows, key=lambda r: r.get("published") or "", reverse=True)
        out = []
        for r in rows[:DIGEST_ITEM_CAP]:
            out.append({
                "title": r.get("title"),
                "summary": r.get("summary"),
                "link": r.get("link"),
                "published": r.get("published"),
                "cues": r.get("cues") or [],
                "mentions": [
                    {
                        "element_id": m["element_id"],
                        "name": (labels.get(m["element_id"]) or {}).get("name") or m.get("name"),
                        # FPL's own line, verbatim. Never our paraphrase of it.
                        "fpl_status": (labels.get(m["element_id"]) or {}).get("status"),
                        "fpl_news": (labels.get(m["element_id"]) or {}).get("news") or "",
                    }
                    for m in (r.get("mentions") or [])
                ],
            })
        if out:
            clubs[club] = out

    scored = evaluate(items, labels)
    return {
        "generated_at": generated_at,
        "n_items": len(items),
        "n_clubs": len(clubs),
        "clubs": dict(sorted(clubs.items())),
        # The page prints these so a reader can judge the feed rather than trust it.
        "quality": {
            "precision": scored["precision"]["rate"],
            "recall": scored["recall"]["rate"],
            "additive": scored["additive"]["count"],
            "fpl_flagged": scored["n_fpl_flagged"],
        },
    }
