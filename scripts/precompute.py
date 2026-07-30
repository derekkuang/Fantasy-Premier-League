#!/usr/bin/env python3
"""Precompute the serving artifact the API reads (per gameweek).

Runs the engine fit once and writes data/serving/gw{gw}.json (xP records + fixture ticker).
Schedule this weekly in production; the API only ever reads its output.

Usage: python scripts/precompute.py [gw] [horizon]     # defaults: gw=1 horizon=5
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpledge.api.precompute import run  # noqa: E402


def main() -> None:
    gw = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    horizon = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    res = run(gw, horizon=horizon)
    m = res["meta"]
    print(f"wrote {res['path']}")
    print(
        f"  gw{m['gw']}  horizon={m['horizon']}  model={m['model_ver']}  "
        f"run_ts={m['run_ts']}  records={m['n_records']}  "
        f"fallback_fixtures={m['fallback_fixtures']}"
    )


if __name__ == "__main__":
    main()
