"""Measuring the numeric guard, rather than asserting it.

`tests/test_brief.py` proves the guard rejects fabricated numbers *that were written by
hand*. That establishes the logic is sound and says nothing about the two things that
decide whether the feature works in production:

  FALSE NEGATIVES — a hallucinated number the guard misses. One reaches the page and the
    product's only real differentiator is gone. Measured here by INJECTION: take briefings
    that passed, corrupt them in ways a language model plausibly would, and count how many
    the guard catches. Known-bad by construction, so this is a true recall number — and it
    needs no API key, so it runs in CI.

  FALSE POSITIVES — correct briefings the guard rejects. Every fixture quietly falls back
    to the template and the LLM layer is dead while the page still looks fine. This is the
    likelier failure and the invisible one. Measured by generating for real and reporting
    the rejection rate, what it was rejected FOR, and whether the retry recovers it.

The second half doubles as the model/effort A/B rig: same fixtures, swap the model, compare
pass rate against cost. That is how the xP model's structural changes were decided, applied
to the narration layer.

Pure functions only — the caller does the I/O (see `scripts/eval_brief.py`).
"""

from __future__ import annotations

import random
import re
from collections import Counter

from .. import brief as B

# USD per million tokens, for cost accounting only. A stale number here misreports the
# cost of a run; it can never affect a briefing.
PRICING = {
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Cost of a run, or None for a model with no price on file (never a guess)."""
    if model not in PRICING:
        return None
    cin, cout = PRICING[model]
    return input_tokens / 1e6 * cin + output_tokens / 1e6 * cout


# --- fixtures ------------------------------------------------------------------------ #
def fact_packs(payload: dict, top_assets: int = 5) -> list[tuple[str, dict]]:
    """[(match_id, fact_pack)] for EVERY fixture in a serving payload.

    `brief_matches` deliberately narrates only the current gameweek — narrating eight weeks
    out would describe projections nobody should act on. The harness is under no such
    constraint: the engine already computed distributions across the whole horizon, so a
    horizon-8 payload yields ~80 distinct packs to measure against instead of ~10.
    """
    by_team: dict = {}
    for r in payload.get("records", []):
        by_team.setdefault(r["team_id"], []).append(r)

    out = []
    for m in payload.get("matches", []):
        pool = by_team.get(m["home_id"], []) + by_team.get(m["away_id"], [])
        assets = [
            {"web_name": r["web_name"], "team": r["team_name"], "position": r["position"],
             "xp": round(r["xp"], 2), "price": r["price"], "ownership": r["ownership"]}
            for r in sorted(pool, key=lambda r: r["xp"], reverse=True)[:top_assets]
        ]
        out.append((m["match_id"], B.fact_pack(m, assets or None, top_assets=top_assets)))
    return out


# --- injection: what the guard actually catches --------------------------------------- #
def _cited(pack: dict, evidence) -> dict:
    return {k: pack[k] for k in evidence if k in pack}


def _swap(text: str, old: str, new: str) -> str | None:
    """Replace the first whole-number occurrence of `old`; None if it isn't there.

    Bounded so "2" in "2-0" replaces the 2 and not the 0, and so "1" never eats the "1"
    inside "21".
    """
    pat = re.compile(r"(?<![\d.])" + re.escape(old) + r"(?![\d])")
    swapped, n = pat.subn(new, text, count=1)
    return swapped if n else None


def _targets(brief: dict):
    """(index, angle) for angles that carry both a number and a citation to corrupt."""
    for i, a in enumerate(brief.get("angles", [])):
        if a.get("evidence") and B.numbers_in(a.get("text", "")):
            yield i, a


def _mutant(brief: dict, i: int, text: str | None = None, evidence=None) -> dict:
    angles = [dict(a) for a in brief["angles"]]
    if text is not None:
        angles[i]["text"] = text
    if evidence is not None:
        angles[i]["evidence"] = evidence
    return {**brief, "angles": angles}


def _digit_drift(brief, pack, rng):
    """The plain case: a real figure restated wrong. 63% becomes 65%."""
    grounded = B.allowed_numbers(pack)
    for i, a in _targets(brief):
        for tok in B.numbers_in(a["text"]):
            raw = tok.rstrip("%").replace(",", "")
            try:
                val = float(raw)
            except ValueError:
                continue
            for delta in (2, 3, 5, 7, 11):
                new = val + delta
                if any(abs(new - g) <= 0.5 for g in grounded):
                    continue
                new_tok = (f"{new:g}" if "." in raw else f"{int(new)}") + ("%" if tok.endswith("%") else "")
                text = _swap(a["text"], tok, new_tok)
                if text:
                    return _mutant(brief, i, text=text), f"{tok} -> {new_tok}"
    return None


def _misattribution(brief, pack, rng):
    """The case that motivated evidence-scoped checking, and the one a pack-wide check
    waves through: a number that IS in the pack, used in a sentence that isn't about it."""
    for i, a in _targets(brief):
        cited = _cited(pack, a["evidence"])
        safe = B.allowed_numbers(cited)
        others = [k for k in pack if k not in a["evidence"]]
        rng.shuffle(others)
        for key in others:
            for tok in B.numbers_in(str(pack[key])):
                try:
                    val = float(tok.rstrip("%").replace(",", ""))
                except ValueError:
                    continue
                if any(abs(val - s) <= 0.5 for s in safe):
                    continue
                text = a["text"] + f" They work {val:g}% of their chances down the left."
                return _mutant(brief, i, text=text), f"borrowed {val:g} from {key}"
    return None


def _arithmetic(brief, pack, rng):
    """Correct arithmetic on two cited values. 63 + 21 = 84 is right and still forbidden:
    the pack has no 84, so nothing verified it."""
    grounded = B.allowed_numbers(pack)
    for i, a in _targets(brief):
        vals = sorted(B.allowed_numbers(_cited(pack, a["evidence"])))
        for x in vals:
            for y in vals:
                total = x + y
                if total == x or any(abs(total - g) <= 0.5 for g in grounded):
                    continue
                text = a["text"] + f" That is {total:g}% between them."
                return _mutant(brief, i, text=text), f"{x:g} + {y:g} = {total:g}"
    return None


def _false_precision(brief, pack, rng):
    """Precision the pack never had. 2.1 becomes 2.14 — a claim to a third significant
    figure the model invented."""
    grounded = B.allowed_numbers(pack)
    for i, a in _targets(brief):
        for tok in B.numbers_in(a["text"]):
            raw = tok.rstrip("%").replace(",", "")
            if "." not in raw:
                continue
            for extra in "47":
                new_tok = raw + extra + ("%" if tok.endswith("%") else "")
                val = float(raw + extra)
                tol = 0.5 * (10 ** -len(new_tok.rstrip("%").split(".")[1]))
                if any(abs(val - g) <= tol for g in grounded):
                    continue
                text = _swap(a["text"], tok, new_tok)
                if text:
                    return _mutant(brief, i, text=text), f"{tok} -> {new_tok}"
    return None


def _phantom_evidence(brief, pack, rng):
    """A citation to a fact that does not exist — the sentence was never grounded at all."""
    for i, a in _targets(brief):
        return _mutant(brief, i, evidence=[*a["evidence"], "possession_pct"]), "cited possession_pct"
    return None


MUTATIONS = {
    "digit_drift": _digit_drift,
    "misattribution": _misattribution,
    "arithmetic": _arithmetic,
    "false_precision": _false_precision,
    "phantom_evidence": _phantom_evidence,
}


def run_mutations(cases, seed: int = 0, kinds=None) -> dict:
    """Corrupt every briefing every way that applies, and count what the guard catches.

    `cases` is [(fact_pack, briefing)] — briefings that already pass. Each mutation is
    built from the pack itself, so "this is ungrounded" is true by construction and never
    by asking the guard: `verify` is the thing under test, not the referee.

    Returns per-kind attempted/detected, the misses in full, and a control count of
    briefings that failed the guard BEFORE any corruption (a false positive, and a reason
    to exclude the case rather than credit the mutation).
    """
    rng = random.Random(seed)
    kinds = kinds or list(MUTATIONS)
    per_kind = {k: {"attempted": 0, "detected": 0} for k in kinds}
    misses, control_failures, skipped = [], [], Counter()

    for pack, brief in cases:
        baseline = B.verify(brief, pack)
        if baseline:
            control_failures.append({"pack": pack.get("most_likely_score"), "problems": baseline})
            continue
        for kind in kinds:
            made = MUTATIONS[kind](brief, pack, rng)
            if made is None:
                skipped[kind] += 1  # briefing offered no suitable target — not a miss
                continue
            mutant, detail = made
            per_kind[kind]["attempted"] += 1
            problems = B.verify(mutant, pack)
            if problems:
                per_kind[kind]["detected"] += 1
            else:
                misses.append({"kind": kind, "detail": detail, "brief": mutant})

    attempted = sum(v["attempted"] for v in per_kind.values())
    detected = sum(v["detected"] for v in per_kind.values())
    return {
        "n_cases": len(cases),
        "n_control_failures": len(control_failures),
        "control_failures": control_failures,
        "per_kind": per_kind,
        "not_applicable": dict(skipped),
        "attempted": attempted,
        "detected": detected,
        "recall": detected / attempted if attempted else None,
        "misses": misses,
    }


# --- live generation ------------------------------------------------------------------ #
def run_live(packs, client=None, repeats: int = 1, model: str = B.MODEL,
             effort: str = B.EFFORT, on_result=None) -> list[dict]:
    """Generate `repeats` briefings per fact pack, keeping every attempt's trace.

    Repeats matter: whether the guard fires is a sampling question, so one generation per
    fixture measures the fixture, not the model. `on_result` is called per generation so a
    long run can stream progress.
    """
    out = []
    for run in range(1, repeats + 1):
        for match_id, pack in packs:
            trace: list = []
            brief = B.narrate(pack, client=client, trace=trace, model=model, effort=effort)
            rec = {
                "fixture": match_id,
                "run": run,
                "attempts": trace,
                "generated_by": brief.get("generated_by"),
                "fell_back": brief.get("generated_by") == "template",
                "brief": brief,
                "pack": pack,
            }
            out.append(rec)
            if on_result:
                on_result(rec)
    return out


def summarise(generations) -> dict:
    """The numbers worth quoting, from a list of `run_live` records."""
    n = len(generations)
    attempts = [a for g in generations for a in g["attempts"]]
    outcomes = Counter(a["outcome"] for a in attempts)

    first_pass = sum(
        1 for g in generations
        if g["attempts"] and g["attempts"][0]["outcome"] == "ok"
    )
    rejected_first = [
        g for g in generations
        if g["attempts"] and g["attempts"][0]["outcome"] == "guard_rejected"
    ]
    # Does feeding the rejection reason back actually work? This is the claim the retry
    # loop makes, and the only place it is tested.
    retry_recovered = sum(
        1 for g in rejected_first
        if any(a["outcome"] == "ok" for a in g["attempts"][1:])
    )

    kinds = Counter(
        B.classify_problem(p)
        for a in attempts for p in a.get("problems", [])
    )
    tin = sum(a.get("usage", {}).get("input_tokens", 0) for a in attempts)
    tout = sum(a.get("usage", {}).get("output_tokens", 0) for a in attempts)
    models = {a["model"] for a in attempts} or {None}
    model = next(iter(models)) if len(models) == 1 else None

    return {
        "n_generations": n,
        "n_attempts": len(attempts),
        "outcomes": dict(outcomes),
        "first_attempt_pass_rate": first_pass / n if n else None,
        "guard_rejection_rate": outcomes["guard_rejected"] / len(attempts) if attempts else None,
        "n_rejected_first": len(rejected_first),
        "retry_success_rate": retry_recovered / len(rejected_first) if rejected_first else None,
        "fallback_rate": sum(1 for g in generations if g["fell_back"]) / n if n else None,
        "problem_kinds": dict(kinds),
        "input_tokens": tin,
        "output_tokens": tout,
        "cost_usd": cost_usd(model, tin, tout) if model else None,
        "model": model,
    }
