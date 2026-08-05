"""Read weekly pre-deadline snapshots back into a form the backtest can score.

`scripts/snapshot.py` captures FPL's live bootstrap before each deadline. This is the other end
of that pipe. It exists now, before there is any data to read, for one reason: the capture starts
2026-08-21 and cannot be backfilled, so the moment a season of snapshots exists somebody will
want to answer two questions that have never been answerable, and neither should be blocked on
writing plumbing then.

  1. WHAT IS AVAILABILITY WORTH? Production scales every projection by `availability_factor`
     (injury status, `chance_of_playing_next_round`). The historical dataset carries no such
     column, so `validate_xp` has always run a version of the model with availability switched
     OFF. Every accuracy figure this project has ever published therefore describes a
     handicapped model, by an unknown margin. `availability_map` + `validate_xp(availability=)`
     closes that.
  2. IS THE BASELINE HONEST? `ep_next` recorded against the deadline it applies to, rather than
     §16's shift of a post-gameweek column back by one week.

THE ONE RULE THIS FILE ENFORCES: a snapshot may only be used for the gameweek it was taken
before. `hours_before_deadline` is recorded at capture time and must be positive; a capture that
landed after kickoff has seen team sheets and would leak the answer into a validation number.
Where several captures exist for one gameweek the LATEST pre-deadline one wins — closest to the
deadline is the most informed, and it is still a forecast.
"""

from __future__ import annotations

import gzip
import json
import pathlib

from .. import config


def _index_path() -> pathlib.Path:
    return config.DATA_DIR / "raw" / "snapshot_index.jsonl"


def load_index(path: pathlib.Path | None = None) -> list[dict]:
    """Every capture ever taken, newest last. Empty if none have run."""
    p = path or _index_path()
    if not p.exists():
        return []
    rows = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def best_capture_per_gameweek(index: list[dict]) -> dict:
    """{gameweek: index_row} — the latest capture taken BEFORE each deadline.

    Captures with a non-positive `hours_before_deadline` are dropped, not merely deprioritised.
    A snapshot taken after the deadline has seen the team sheet; using it would manufacture a
    validation number that cannot be reproduced live, which is the exact failure §16 was about.
    """
    best: dict = {}
    for row in index:
        gw, hours = row.get("for_gameweek"), row.get("hours_before_deadline")
        if gw is None or hours is None or hours <= 0:
            continue
        current = best.get(gw)
        if current is None or hours < current["hours_before_deadline"]:
            best[gw] = row
    return best


def _read_bootstrap(row: dict) -> dict | None:
    for p in row.get("paths", []):
        if "bootstrap_snapshot" in p and pathlib.Path(p).exists():
            with gzip.open(p, "rt", encoding="utf-8") as fh:
                return json.load(fh)
    return None


def availability_map(index: list[dict] | None = None) -> dict:
    """{(gameweek, element_id): {"chance_of_playing", "status", "ep_next"}}.

    `chance_of_playing` is FPL's `chance_of_playing_next_round` as a percentage or None, which is
    exactly what `models.minutes.availability_factor` expects — the mapping is deliberately not
    reinterpreted here, so the backtest applies the identical function production applies.
    """
    rows = load_index() if index is None else index
    out: dict = {}
    for gw, row in best_capture_per_gameweek(rows).items():
        bootstrap = _read_bootstrap(row)
        if not bootstrap:
            continue
        for p in bootstrap.get("elements", []):
            chance = p.get("chance_of_playing_next_round")
            out[(gw, p["id"])] = {
                "chance_of_playing": None if chance is None else float(chance),
                "status": p.get("status") or "a",
                "ep_next": float(p.get("ep_next") or 0.0),
            }
    return out


def coverage(availability: dict, gameweeks) -> dict:
    """What fraction of the requested gameweeks a snapshot actually exists for.

    Reported rather than assumed, for the §13 reason: a metric averaged over gameweeks the
    feature only covers half of is not the metric it claims to be.
    """
    have = {gw for gw, _el in availability}
    want = set(gameweeks)
    return {
        "gameweeks_wanted": len(want),
        "gameweeks_covered": len(want & have),
        "share": round(len(want & have) / len(want), 3) if want else 0.0,
        "missing": sorted(want - have),
    }
