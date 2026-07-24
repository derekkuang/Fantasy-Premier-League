"""FPL <-> external-source (Understat/FBref) identity mapping.

The single fiddliest, most leakage-prone join in the project: matching external xG
players/teams to FPL's `element_id`. Names differ ("Son" vs "Son Heung-min"),
carry accents and special letters ("Ødegaard", "Kanté"), and the same surname
recurs. A wrong join silently corrupts every downstream feature, so this is a
first-class, TESTED artifact — not an afterthought.

Strategy: normalise names (accents + special letters + punctuation), score with a
blend of sequence similarity and token overlap, restrict to same team when known,
and keep an explicit override table for the handful the fuzzy matcher gets wrong.
Stdlib-only, so the test suite needs no extra dependency.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from difflib import SequenceMatcher

# Letters with no canonical NFKD decomposition — map explicitly (lowercase input).
_SPECIAL = {
    "ø": "o", "ł": "l", "æ": "ae", "œ": "oe", "ß": "ss",
    "đ": "d", "ð": "d", "þ": "th", "ı": "i", "ĸ": "k",
}


def normalize_name(name: str) -> str:
    """Lowercase, strip accents/special letters and punctuation, collapse spaces."""
    n = name.lower()
    n = "".join(_SPECIAL.get(ch, ch) for ch in n)
    n = unicodedata.normalize("NFKD", n)
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = re.sub(r"[^a-z\s]", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def name_similarity(a: str, b: str) -> float:
    """Blend of character sequence ratio and token overlap in [0, 1].

    Token overlap lets a short alias ("Son") match a full name ("Son Heung-min")
    that a raw sequence ratio would miss.
    """
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    seq = SequenceMatcher(None, na, nb).ratio()
    ta, tb = set(na.split()), set(nb.split())
    tok = len(ta & tb) / min(len(ta), len(tb))
    return max(seq, tok)


def match_players(
    fpl_players: Sequence[dict],
    ext_players: Sequence[dict],
    overrides: dict | None = None,
    threshold: float = 0.6,
) -> tuple[dict, list]:
    """Map external ids -> FPL element_ids.

    Args:
        fpl_players: dicts with keys element_id, name, team (team optional).
        ext_players: dicts with keys ext_id, name, team (team optional).
        overrides:   {ext_id: element_id} manual fixes that bypass fuzzy matching.
        threshold:   minimum similarity to accept an automatic match.

    Returns (mapping, unmatched_ext_ids). Anything below threshold is left
    UNMATCHED rather than force-matched — an honest gap you review, not a silent
    wrong join.
    """
    overrides = overrides or {}
    mapping: dict = {}
    unmatched: list = []

    for e in ext_players:
        if e["ext_id"] in overrides:
            mapping[e["ext_id"]] = overrides[e["ext_id"]]
            continue

        # Soft team filter: prefer same-team candidates, fall back to all.
        e_team = normalize_name(e["team"]) if e.get("team") else None
        same_team = [
            f for f in fpl_players if e_team and f.get("team") and normalize_name(f["team"]) == e_team
        ]
        candidates = same_team or list(fpl_players)

        best, best_score = None, 0.0
        for f in candidates:
            s = name_similarity(e["name"], f["name"])
            if s > best_score:
                best, best_score = f, s

        if best is not None and best_score >= threshold:
            mapping[e["ext_id"]] = best["element_id"]
        else:
            unmatched.append(e["ext_id"])

    return mapping, unmatched
