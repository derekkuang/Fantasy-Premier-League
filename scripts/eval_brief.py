#!/usr/bin/env python3
"""Measure the briefing guard: injection recall offline, generation quality live.

The injection pass needs no API key and no network — it corrupts briefings the guard
already passed and reports how many it catches. That is the recall number.

The live pass generates for real and reports what fraction of briefings the guard rejects,
what it rejected them FOR, whether the retry recovers them, and what a gameweek costs. It
is also the model/effort A/B rig: run it twice with --model and compare.

Usage:
  python scripts/eval_brief.py                       # injection only (no key needed)
  python scripts/eval_brief.py --live --repeats 5    # + generate against the real API
  python scripts/eval_brief.py --live --model claude-haiku-4-5 --effort low
  python scripts/eval_brief.py --gw 1 --limit 20 --out data/eval/brief.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import UTC, datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpledge import brief as B
from fpledge.api import store
from fpledge.eval import brief_eval as E


def _pct(x) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def _load_packs(gw: int | None, limit: int | None):
    gws = [gw] if gw else store.available_gws()
    if not gws:
        sys.exit(
            "no serving artifact found — run `make precompute` first "
            "(or point FPLEDGE_SERVING_DIR at one)."
        )
    packs = []
    for g in gws:
        payload = store.read_gw(g)
        if payload:
            packs.extend(E.fact_packs(payload))
    if not packs:
        sys.exit(f"serving artifact for gw{gws[0]} has no matches.")
    return packs[:limit] if limit else packs


def _report_injection(res: dict) -> None:
    print(f"\n=== INJECTION — does the guard catch a corrupted briefing? "
          f"({res['n_cases']} briefings) ===")
    if res["n_control_failures"]:
        # A briefing that fails BEFORE corruption is a false positive: the guard rejecting
        # correct copy. That is the failure mode nobody notices, so it leads the report.
        print(f"  !! {res['n_control_failures']} briefing(s) failed the guard UNCORRUPTED "
              "(false positive — excluded from recall)")
        for f in res["control_failures"][:3]:
            print(f"       {f['problems'][0]}")
    if not res["attempted"]:
        print("  no mutations applied — briefings offered no corruptible target.")
        return
    print(f"  recall: {res['detected']}/{res['attempted']} = {_pct(res['recall'])}\n")
    for kind, v in res["per_kind"].items():
        n, d = v["attempted"], v["detected"]
        na = res["not_applicable"].get(kind, 0)
        skip = f"  ({na} n/a)" if na else ""
        rate = _pct(d / n) if n else "n/a"
        print(f"    {kind:18} {d:4}/{n:<4} {rate:>7}{skip}")
    if res["misses"]:
        print(f"\n  MISSED ({len(res['misses'])}) — each of these would reach a reader:")
        for m in res["misses"][:5]:
            print(f"    [{m['kind']}] {m['detail']}")


def _report_live(summary: dict) -> None:
    print(f"\n=== LIVE GENERATION — {summary['model']} "
          f"({summary['n_generations']} briefings, {summary['n_attempts']} attempts) ===")
    print(f"  first-attempt pass    {_pct(summary['first_attempt_pass_rate'])}")
    print(f"  guard rejection rate  {_pct(summary['guard_rejection_rate'])}  (per attempt)")
    print(f"  retry recovered       {_pct(summary['retry_success_rate'])}  "
          f"(of {summary['n_rejected_first']} rejected first time)")
    print(f"  fell back to template {_pct(summary['fallback_rate'])}")
    if summary["problem_kinds"]:
        print("\n  why the guard fired (this is what to fix):")
        for kind, n in sorted(summary["problem_kinds"].items(), key=lambda kv: -kv[1]):
            print(f"    {kind:22} {n}")
    if summary["outcomes"]:
        print(f"\n  attempt outcomes: {summary['outcomes']}")
    cost = summary["cost_usd"]
    print(f"\n  tokens {summary['input_tokens']} in / {summary['output_tokens']} out"
          + (f"   cost ${cost:.4f}" if cost is not None else "   cost n/a (no price on file)"))
    if summary["n_generations"]:
        per = (cost / summary["n_generations"]) if cost is not None else None
        if per is not None:
            print(f"  ${per:.4f} per briefing  ->  ~${per * 10:.3f} per gameweek (10 fixtures)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gw", type=int, help="gameweek artifact to read (default: all present)")
    ap.add_argument("--limit", type=int, help="cap the number of fixtures")
    ap.add_argument("--live", action="store_true", help="also generate against the real API")
    ap.add_argument("--repeats", type=int, default=1, help="generations per fixture (live)")
    ap.add_argument("--model", default=B.MODEL)
    ap.add_argument("--effort", default=B.EFFORT)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", help="write the full run log to this JSON path")
    args = ap.parse_args()

    packs = _load_packs(args.gw, args.limit)
    print(f"{len(packs)} fact pack(s) loaded.")

    if args.live:
        client = B._client()
        if client is None:
            sys.exit(
                "--live needs a working client: set ANTHROPIC_API_KEY and "
                'install the SDK with `pip install -e ".[llm]"`.'
            )
        n = len(packs) * args.repeats
        print(f"generating {n} briefing(s) with {args.model} (effort={args.effort})...")
        done = [0]

        def tick(rec):
            done[0] += 1
            mark = "." if not rec["fell_back"] else "F"
            print(mark, end="", flush=True)
            if done[0] % 50 == 0:
                print(f" {done[0]}/{n}", flush=True)

        generations = E.run_live(packs, client=client, repeats=args.repeats,
                                 model=args.model, effort=args.effort, on_result=tick)
        print()
    else:
        # No API: the template is a briefing the guard is meant to pass, so it seeds the
        # injection pass. Weaker inputs than model prose, but the recall number is real
        # and it runs anywhere.
        print("no --live: seeding injection from the deterministic template renderer.")
        generations = [
            {"fixture": mid, "run": 1, "attempts": [], "generated_by": "template",
             "fell_back": True, "brief": B.render_template(pack), "pack": pack}
            for mid, pack in packs
        ]

    cases = [(g["pack"], g["brief"]) for g in generations]
    injection = E.run_mutations(cases, seed=args.seed)
    _report_injection(injection)

    summary = None
    if args.live:
        summary = E.summarise(generations)
        _report_live(summary)

    if args.out:
        path = pathlib.Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "run_ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "model": args.model,
            "effort": args.effort,
            "live": args.live,
            "injection": injection,
            "live_summary": summary,
            "generations": generations,
        }, indent=2))
        print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
