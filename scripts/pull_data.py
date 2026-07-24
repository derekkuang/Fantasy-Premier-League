#!/usr/bin/env python3
"""Pull core FPL data and land it, immutable + timestamped, in data/raw/.

Usage:
    python scripts/pull_data.py            # bootstrap-static + fixtures
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpledge.ingest import landing  # noqa: E402
from fpledge.ingest.fpl_api import FPLClient  # noqa: E402


def main() -> None:
    client = FPLClient()

    boot = client.bootstrap_static()
    fp1 = landing.land(boot, source="fpl_api", endpoint="bootstrap")
    print(f"landed bootstrap-static -> {fp1}")

    fixtures = client.fixtures()
    fp2 = landing.land(fixtures, source="fpl_api", endpoint="fixtures")
    print(f"landed fixtures        -> {fp2}")

    n_players = len(boot.get("elements", []))
    n_teams = len(boot.get("teams", []))
    print(f"ok: landed {n_teams} teams, {n_players} players, {len(fixtures)} fixtures")


if __name__ == "__main__":
    main()
