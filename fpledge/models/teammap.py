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
