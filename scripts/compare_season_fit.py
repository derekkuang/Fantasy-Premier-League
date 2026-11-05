#!/usr/bin/env python3
"""Replay past seasons with the engine frozen and rolling, and apply the pre-registered rule.

The method and the decision rule are in `fpledge/eval/season_fit.py`. Offline: it reads
football-data's published results and changes nothing in production.

Usage: python scripts/compare_season_fit.py              development seasons, plain rolling fit
       python scripts/compare_season_fit.py --held-out   the fixed candidate; runs once only
"""

from __future__ import annotations

import json
import pathlib
import sys
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpledge import config
from fpledge.eval import season_fit
from fpledge.ingest import footballdata
from fpledge.models.dixon_coles import DixonColesModel

CODES = ["2021", "2122", "2223", "2324", "2425", "2526", "2627"]
TEST_SEASONS = ["2023-24", "2024-25", "2025-26"]
THIS_SEASON = "2026-27"    # reported for direction only; it plays no part in the verdict
OUT = config.DATA_DIR / "eval" / "season_fit.json"

# Three more seasons than are scored: the first scored season needs its three priors.
HELD_OUT_CODES = ["1516", "1617", "1718", "1819", "1920", "2021", "2122", "2223"]
HELD_OUT_SEASONS = ["2018-19", "2019-20", "2020-21", "2021-22", "2022-23"]
HELD_OUT_OUT = config.DATA_DIR / "eval" / "season_fit_held_out.json"


def _line(label: str, res: dict | None) -> str:
    if res is None:
        return f"    {label:<12} no matches"
    lo, hi = res["ci"]
    flag = "better" if hi < 0 else "worse" if lo > 0 else "-"
    return (f"    {label:<12} n={res['n']:<5} frozen {res['frozen']:.4f}  rolling {res['rolling']:.4f}"
            f"  diff {res['diff']:+.4f}  [{lo:+.4f}, {hi:+.4f}]  {flag}")


def _print(summary: dict) -> None:
    print(f"market's own log-loss on these matches: {summary['market_log_loss']:.4f}")
    for h, block in summary["horizons"].items():
        print(f"\n=== cut-off {h} days before kickoff ===")
        for metric, res in block.items():
            print(f"  {metric}")
            print(_line("pooled", res["pooled"]))
            for name in ("seasons", "stages"):
                for key, r in res[name].items():
                    print(_line(key, r))
            print(_line("new clubs", res["new_clubs"]))
            print(_line("known clubs", res["known_clubs"]))


def _replay_candidate(job: tuple[list[dict], str]) -> list[dict]:
    matches, season = job
    return season_fit.replay_season(matches, season, season_fit.CandidateEngine,
                                    baseline_factory=DixonColesModel)


def held_out() -> None:
    """The candidate against production, on seasons that played no part in choosing it."""
    if HELD_OUT_OUT.exists():
        raise SystemExit(f"{HELD_OUT_OUT} exists, so this test has been run. These seasons only "
                         "count once: see the module docstring of fpledge/eval/season_fit.py.")
    matches, report = footballdata.load_seasons_report(HELD_OUT_CODES)
    if report["failed"]:
        raise SystemExit(f"missing seasons: {report['failed']}")

    jobs = [(matches, season) for season in HELD_OUT_SEASONS]
    with ProcessPoolExecutor(max_workers=len(jobs)) as pool:
        rows = [row for part in pool.map(_replay_candidate, jobs) for row in part]
    summary = season_fit.summarise(rows)
    decision = season_fit.verdict(summary)

    HELD_OUT_OUT.parent.mkdir(parents=True, exist_ok=True)
    HELD_OUT_OUT.write_text(json.dumps({"verdict": decision, "summary": summary}, indent=2))
    _print(summary)
    print(f"\nVERDICT: {decision['decision']}")
    for reason in decision["reasons"]:
        print(f"  - {reason}")
    print(f"\nwrote {HELD_OUT_OUT}")


def main() -> None:
    if "--held-out" in sys.argv[1:]:
        held_out()
        return

    matches, report = footballdata.load_seasons_report(CODES)
    if report["failed"]:
        raise SystemExit(f"missing seasons: {report['failed']}")

    rows = []
    for season in TEST_SEASONS:
        print(f"replaying {season}...", flush=True)
        rows += season_fit.replay_season(matches, season, DixonColesModel)
    summary = season_fit.summarise(rows)
    _print(summary)

    print(f"\nreplaying {THIS_SEASON} (direction only, not part of the verdict)...", flush=True)
    current = season_fit.replay_season(matches, THIS_SEASON, DixonColesModel)
    this_season = season_fit.summarise(current)
    _print(this_season)

    decision = season_fit.verdict(summary)
    print(f"\nVERDICT: {decision['decision']}")
    for reason in decision["reasons"]:
        print(f"  - {reason}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"verdict": decision, "summary": summary,
                               "this_season": this_season}, indent=2))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
