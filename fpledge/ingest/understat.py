"""xG ingestion via `soccerdata` (Understat / FBref), plus the ID-mapping problem.

The fiddliest, most under-rated piece of this whole project is joining
Understat/FBref player & team identities to FPL's `element_id`/`team` — names
differ ("Son" vs "Son Heung-min"), and a bad join silently corrupts every
downstream feature. Treat the mapping as a first-class, tested artifact.

`soccerdata` is a declared dependency, imported lazily. This module is a
deliberate stub: wire it up in Phase 0/1 against a season of data.
"""

from __future__ import annotations


def fetch_understat_team_xg(seasons):  # noqa: ANN001
    """Return per-match team xG-for / xG-against (feeds the match engine).

    TODO(phase-1): implement with soccerdata.Understat; land raw via ingest.landing.
    """
    import soccerdata as sd  # noqa: PLC0415, F401

    raise NotImplementedError("wire up soccerdata.Understat in Phase 1")


def build_fpl_id_map(fpl_players, understat_players):  # noqa: ANN001
    """Map Understat player ids -> FPL element_ids.

    TODO(phase-1): fuzzy-match on normalised name + team + position, then persist a
    reviewed override table. Add a test that asserts a known set of stars map
    correctly (this is where leakage/accuracy bugs hide).
    """
    raise NotImplementedError("build and TEST the FPL<->Understat id map in Phase 1")
