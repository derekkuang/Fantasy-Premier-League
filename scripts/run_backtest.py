#!/usr/bin/env python3
"""Run a walk-forward backtest of the match engine and print 1X2 metrics.

This entrypoint wires the harness. Until the DuckDB tables are populated (Phase 0),
it runs a tiny SYNTHETIC demo so the loop is exercisable end-to-end today.

Usage:
    python scripts/run_backtest.py
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpledge.eval.backtest import run_walk_forward  # noqa: E402
from fpledge.models.match_engine import DixonColesEngine  # noqa: E402

# --- Synthetic demo data (replace with DuckDB-backed callbacks in Phase 1) --- #
_MATCHES = [
    {"home": "A", "away": "B", "home_goals": 2, "away_goals": 0, "date": "2025-08-16"},
    {"home": "B", "away": "C", "home_goals": 1, "away_goals": 1, "date": "2025-08-17"},
    {"home": "C", "away": "A", "home_goals": 0, "away_goals": 3, "date": "2025-08-23"},
    {"home": "A", "away": "C", "home_goals": 1, "away_goals": 1, "date": "2025-08-24"},
]
_GW2 = [{"home": "A", "away": "B", "home_goals": 2, "away_goals": 1, "date": "2025-08-30"}]


def main() -> None:
    results = run_walk_forward(
        gameweeks=[2],
        matches_before=lambda gw: _MATCHES,      # POINT-IN-TIME in the real version
        fixtures_in=lambda gw: _GW2,
        engine_factory=DixonColesEngine,
        experiment=None,  # set to "fpledge-backtest" once MLflow is installed
    )
    print("walk-forward demo results:")
    for k in ("n", "log_loss", "brier"):
        print(f"  {k:10s}: {results[k]}")
    print(f"  calibration bins: {len(results['calibration_home'])}")
    print("\n(Synthetic demo — populate DuckDB and swap the callbacks for real results.)")


if __name__ == "__main__":
    main()
