#!/usr/bin/env python3
"""Real walk-forward backtest of the from-scratch Dixon-Coles engine on EPL results.

Downloads several completed seasons (results + closing odds) from Football-Data.co.uk,
fits the time-decayed Dixon-Coles MLE on an expanding point-in-time window, and reports
model vs MARKET log-loss/Brier, home-win calibration, and an honest ROI-vs-closing-line.

Usage:
    python scripts/run_backtest.py
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpledge.eval.backtest import walk_forward  # noqa: E402
from fpledge.ingest import footballdata  # noqa: E402
from fpledge.models.dixon_coles import DixonColesModel  # noqa: E402
from fpledge.storage import duck  # noqa: E402
from fpledge.storage import load as storeload  # noqa: E402

SEASONS = ["2324", "2425", "2526"]  # 2023/24, 2024/25, 2025/26


def main() -> None:
    print("downloading historical results (Football-Data.co.uk)...")
    matches = footballdata.load_seasons(SEASONS)
    if not matches:
        print("no data downloaded; aborting.")
        return
    print(f"  total: {len(matches)} matches")

    con = duck.connect()
    duck.init_schema(con)
    storeload.load_hist_matches(con, matches)
    con.close()

    test_season = max(m["season"] for m in matches)
    test_start = min(m["date_ord"] for m in matches if m["season"] == test_season)

    res = walk_forward(matches, test_start, DixonColesModel, refit_every=20)

    print(f"\n=== WALK-FORWARD BACKTEST — test season {test_season} ===")
    print(f"  matches scored : {res['n']}  (skipped {res['skipped_unknown_team']} unknown-team)")
    print(f"  MODEL   log-loss {res['model_log_loss']:.4f}   Brier {res['model_brier']:.4f}")
    if res.get("market_log_loss") is not None:
        print(f"  MARKET  log-loss {res['market_log_loss']:.4f}   Brier {res['market_brier']:.4f}"
              "   <- de-vigged closing line, the benchmark to beat")
        edge = res["market_log_loss"] - res["model_log_loss"]
        verdict = "model edge" if edge > 0 else "NO edge (expected)"
        print(f"  log-loss gap   : {edge:+.4f}  ({verdict})")
    if res.get("bet_n"):
        print(f"  bets vs close  : {res['bet_n']} flat-stake bets, ROI {res['bet_roi'] * 100:+.1f}%"
              f"  ({res['bet_profit_units']:+.1f} units)")
        print("  honest read    : ROI ~0/negative = the market is efficient. That is the deliverable,")
        print("                   not a failure. CLV, not this backtest ROI, is the real live metric.")
    print(f"  home-win calibration bins: {len(res['calibration_home'])}")


if __name__ == "__main__":
    main()
