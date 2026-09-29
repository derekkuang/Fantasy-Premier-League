"""FPL team names <-> Football-Data team names.

The match engine is fitted on Football-Data results, so to predict FPL fixtures we must
map FPL's team names ("Man Utd", "Spurs") to Football-Data's ("Man United", "Tottenham").
Reuses the fuzzy name matcher from `ingest.idmap`, with a small manual override table for
the handful fuzzy matching can't get. Teams with no confident match (e.g. promoted sides
absent from the engine's history) map to None and are skipped by the caller.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..ingest import idmap

# Cases the fuzzy matcher gets wrong (different words for the same club).
FPL_TO_FD_OVERRIDES = {
    "Spurs": "Tottenham",
    "Man Utd": "Man United",
    "Nott'm Forest": "Nott'm Forest",
}


# Odds feeds name clubs their own way: football-data's upcoming file uses short forms
# ("Man United", "Tottenham"), The Odds API uses full ones ("Manchester United", "Tottenham
# Hotspur"). Measured against the FPL names, the fuzzy matcher puts "Manchester United" at 0.583
# and "Tottenham Hotspur" at 0.467 — both under threshold — so these two need saying out loud.
ODDS_TO_FPL_OVERRIDES = {
    "Man United": "Man Utd",
    "Manchester United": "Man Utd",
    "Manchester City": "Man City",
    "Tottenham": "Spurs",
    "Tottenham Hotspur": "Spurs",
    "Nottingham Forest": "Nott'm Forest",
}


def build_odds_team_map(
    fpl_names: Sequence[str], odds_names: Sequence[str], threshold: float = 0.6
) -> dict:
    """{odds-feed name -> FPL name} for the clubs an odds feed is currently pricing.

    WHY THIS IS NOT `build_team_map`. That one answers "which Football-Data side is this FPL
    club, in the seasons the engine was fitted on" — and a promoted club correctly answers
    "none", because it has no top-flight history to fit. Odds are a different question: a
    bookmaker prices Coventry v Arsenal whether or not Coventry has ever been in the division.
    Reusing the engine's map for odds meant newly promoted sides could never be priced from the
    market — the exact clubs the engine is weakest on — while their prices sat unread.

    Matching runs odds-name-first and STABLE: overrides claim their FPL club, then every
    remaining pair is taken in descending similarity, and neither side can be claimed twice.
    That is what makes a partial slate safe. "Man Utd" scores 0.667 against "Man City" — above
    threshold — so on a week where City play and United do not, a naive best-match hands City's
    odds to United. Under stable matching City claims itself at 1.000 first and United, having
    no feed name of its own, simply goes unpriced.
    """
    fpl = list(fpl_names)
    fpl_set = set(fpl)
    out: dict = {}
    taken: set = set()

    pending = []
    for o in odds_names:
        target = ODDS_TO_FPL_OVERRIDES.get(o)
        if target and target in fpl_set and target not in taken:
            out[o] = target
            taken.add(target)
        else:
            pending.append(o)

    scored = sorted(
        ((idmap.name_similarity(f, o), o, f) for o in pending for f in fpl),
        key=lambda t: (-t[0], t[1], t[2]),   # deterministic: score, then names
    )
    for score, o, f in scored:
        if score < threshold or o in out or f in taken:
            continue
        out[o] = f
        taken.add(f)
    return out


def build_team_map(
    fpl_names: Sequence[str], fd_names: Sequence[str], threshold: float = 0.6
) -> dict:
    """Map each FPL team name -> a Football-Data name (or None if no confident match)."""
    fd_set = set(fd_names)
    mapping: dict = {}
    for f in fpl_names:
        override = FPL_TO_FD_OVERRIDES.get(f)
        if override and override in fd_set:
            mapping[f] = override
            continue
        best, best_score = None, 0.0
        for fd in fd_names:
            s = idmap.name_similarity(f, fd)
            if s > best_score:
                best, best_score = fd, s
        mapping[f] = best if best_score >= threshold else None
    return mapping
