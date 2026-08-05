"""The harness that measures the guard.

Two things need testing here. The mutations must produce briefings that are genuinely
ungrounded — a mutation that accidentally writes a real number would be scored as a guard
MISS when the guard was right, which would quietly understate recall. And the trace must
distinguish a guard rejection from an API failure, since telling those apart is the only
reason the trace exists.
"""

from __future__ import annotations

import random

from test_brief import ASSETS, MATCH  # same fixture the guard's own tests use

from fpledge import brief
from fpledge.eval import brief_eval as E


def _pack():
    return brief.fact_pack(MATCH, ASSETS)


def _clean(pack):
    """A briefing that passes the guard — the starting point for every mutation."""
    return brief.render_template(pack)


# --- the mutations themselves ---------------------------------------------------------- #
def test_every_mutation_applies_to_a_template_briefing():
    """If a mutation silently never fires, its recall column reads 0/0 and the gap in
    coverage is invisible."""
    pack, b = _pack(), _clean(_pack())
    for kind, fn in E.MUTATIONS.items():
        assert fn(b, pack, random.Random(0)) is not None, f"{kind} produced no mutant"


def test_mutations_are_ungrounded_by_construction():
    """The mutation must be wrong on the pack's own terms, established WITHOUT consulting
    `verify` — the guard is what's under test, it can't also be the referee."""
    pack, b = _pack(), _clean(_pack())
    for kind, fn in E.MUTATIONS.items():
        if kind == "phantom_evidence":
            continue  # corrupts the citation, not a number
        mutant, _ = fn(b, pack, random.Random(0))
        original = {a["text"] for a in b["angles"]}
        changed = [a for a in mutant["angles"] if a["text"] not in original]
        assert changed, f"{kind} changed no text"
        for angle in changed:
            cited = {k: pack[k] for k in angle["evidence"] if k in pack}
            assert brief.unsupported_numbers(angle["text"], cited), (
                f"{kind} produced a number the fact pack actually supports"
            )


def test_misattribution_borrows_a_real_pack_number():
    """The distinguishing case: pack-wide checking passes it, evidence-scoped catches it.
    If the borrowed number weren't real, this would just be another fabrication test."""
    pack, b = _pack(), _clean(_pack())
    mutant, _ = E._misattribution(b, pack, random.Random(0))
    angle = next(a for a in mutant["angles"]
                 if a["text"] not in {x["text"] for x in b["angles"]})
    assert brief.unsupported_numbers(angle["text"], pack) == []  # grounded pack-wide
    assert brief.verify(mutant, pack)                            # caught anyway


def test_guard_catches_every_mutation_of_the_template():
    """Recall on the one corpus available with no API key."""
    packs = [_pack()]
    res = E.run_mutations([(p, _clean(p)) for p in packs])
    assert res["attempted"] == len(E.MUTATIONS)
    assert res["recall"] == 1.0, res["misses"]


def test_a_briefing_that_fails_before_corruption_is_excluded_not_credited():
    """A false positive must not be laundered into recall — the case is dropped and
    reported, because a guard that rejects correct copy is the quieter failure."""
    pack = _pack()
    bad = {"headline": "Alpha are 77% to win", "angles": [
        {"text": "Alpha are 63% to win.", "evidence": ["home_win_pct"]},
    ]}
    res = E.run_mutations([(pack, bad)])
    assert res["n_control_failures"] == 1
    assert res["attempted"] == 0


def test_run_mutations_is_deterministic():
    pack = _pack()
    cases = [(pack, _clean(pack))]
    a = E.run_mutations(cases, seed=7)
    b = E.run_mutations(cases, seed=7)
    assert a["per_kind"] == b["per_kind"]


# --- the problem taxonomy -------------------------------------------------------------- #
def test_every_verify_failure_classifies_to_a_known_kind():
    """`classify_problem` reads strings `verify` writes. Change one without the other and
    the taxonomy silently degrades to 'other' — this is the pin."""
    pack = _pack()
    briefs = [
        {"headline": "x", "angles": []},                                    # no_angles
        {"headline": "Alpha win 77%.", "angles": [                          # headline_number
            {"text": "Alpha win 63%.", "evidence": ["home_win_pct"]}]},
        {"headline": "x", "angles": [                                       # unknown_evidence_key
            {"text": "Alpha win 63%.", "evidence": ["possession_pct"]}]},
        {"headline": "x", "angles": [                                       # uncited_number
            {"text": "Alpha attack 41% down the left.", "evidence": ["home_win_pct"]}]},
    ]
    seen = set()
    for b in briefs:
        problems = brief.verify(b, pack)
        assert problems
        for p in problems:
            kind = brief.classify_problem(p)
            assert kind != "other", p
            seen.add(kind)
    assert seen == set(brief.PROBLEM_KINDS)


# --- the trace ------------------------------------------------------------------------- #
class _Resp:
    def __init__(self, text=None, stop_reason=None, usage=(120, 45)):
        self.content = [] if text is None else [type("B", (), {"type": "text", "text": text})()]
        self.stop_reason = stop_reason
        self.stop_details = type("D", (), {"category": "cyber"})()
        self.usage = type("U", (), {"input_tokens": usage[0], "output_tokens": usage[1]})()


class _Client:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0
        self.messages = self

    def create(self, **kw):
        self.calls += 1
        r = self.responses[min(self.calls - 1, len(self.responses) - 1)]
        if isinstance(r, Exception):
            raise r
        return r


GOOD = ('{"headline": "Alpha 63% to win", "angles": '
        '[{"text": "Alpha are 63% to win.", "evidence": ["home_win_pct"]}, '
        '{"text": "Draw at 21%.", "evidence": ["draw_pct"]}]}')
HALLUCINATED = ('{"headline": "h", "angles": [{"text": "Alpha attack 77% down the left.", '
                '"evidence": ["home_win_pct"]}]}')


def test_trace_records_a_pass_with_usage():
    trace = []
    brief.narrate(_pack(), client=_Client(_Resp(GOOD)), trace=trace)
    assert [a["outcome"] for a in trace] == ["ok"]
    assert trace[0]["usage"] == {"input_tokens": 120, "output_tokens": 45}


def test_trace_separates_a_guard_rejection_from_an_api_failure():
    """Both end on the template, so the returned briefing cannot tell them apart. If the
    trace can't either, a dead API key reads as a 100% hallucination rate."""
    guard, api = [], []
    brief.narrate(_pack(), client=_Client(_Resp(HALLUCINATED)), trace=guard)
    brief.narrate(_pack(), client=_Client(RuntimeError("network down")), trace=api)
    assert [a["outcome"] for a in guard] == ["guard_rejected", "guard_rejected"]
    assert [a["outcome"] for a in api] == ["api_error"]
    assert "RuntimeError" in api[0]["detail"]


def test_a_refusal_is_not_reported_as_a_parse_error():
    """A declined request is a SUCCESSFUL response with no text block. Read content first
    and it raises, and a safety refusal is filed as malformed output."""
    trace = []
    out = brief.narrate(_pack(), client=_Client(_Resp(None, stop_reason="refusal")), trace=trace)
    assert [a["outcome"] for a in trace] == ["refusal"]
    assert trace[0]["detail"] == "cyber"
    assert out["generated_by"] == "template"


def test_trace_records_malformed_output_as_a_parse_error():
    trace = []
    brief.narrate(_pack(), client=_Client(_Resp("{not json")), trace=trace)
    assert [a["outcome"] for a in trace] == ["parse_error"]


def test_retry_recovery_is_visible_in_the_trace():
    trace = []
    brief.narrate(_pack(), client=_Client(_Resp(HALLUCINATED), _Resp(GOOD)), trace=trace)
    assert [a["outcome"] for a in trace] == ["guard_rejected", "ok"]


def test_model_and_effort_are_overridable_for_ab_runs():
    trace = []
    out = brief.narrate(_pack(), client=_Client(_Resp(GOOD)), trace=trace,
                        model="claude-haiku-4-5", effort="medium")
    assert out["generated_by"] == "claude-haiku-4-5"
    assert trace[0]["model"] == "claude-haiku-4-5" and trace[0]["effort"] == "medium"


def test_narrate_without_a_trace_is_unchanged():
    """Production passes no trace; the tracing must be pure overhead there."""
    out = brief.narrate(_pack(), client=_Client(_Resp(GOOD)))
    assert out["generated_by"] == brief.MODEL and out["attempts"] == 1


# --- aggregation ----------------------------------------------------------------------- #
def _gen(*outcomes, fell_back=False, problems=None):
    return {
        "fixture": "1-1-2", "run": 1, "fell_back": fell_back, "generated_by": "m",
        "brief": {}, "pack": {},
        "attempts": [
            {"attempt": i + 1, "model": "claude-opus-5", "effort": "low", "outcome": o,
             "usage": {"input_tokens": 100, "output_tokens": 50},
             **({"problems": problems} if o == "guard_rejected" and problems else {})}
            for i, o in enumerate(outcomes)
        ],
    }


def test_summarise_reports_the_headline_rates():
    gens = [
        _gen("ok"),
        _gen("ok"),
        _gen("guard_rejected", "ok"),
        _gen("guard_rejected", "guard_rejected", fell_back=True),
    ]
    s = E.summarise(gens)
    assert s["n_generations"] == 4
    assert s["first_attempt_pass_rate"] == 0.5
    assert s["n_rejected_first"] == 2
    assert s["retry_success_rate"] == 0.5     # one of the two rejections recovered
    assert s["fallback_rate"] == 0.25
    assert s["guard_rejection_rate"] == 3 / 6


def test_summarise_costs_the_run_from_the_model_that_ran():
    s = E.summarise([_gen("ok")])
    assert s["cost_usd"] == 100 / 1e6 * 5.0 + 50 / 1e6 * 25.0


def test_cost_is_none_rather_than_guessed_for_an_unpriced_model():
    assert E.cost_usd("some-future-model", 1000, 1000) is None


def test_summarise_buckets_rejections_by_kind():
    gens = [_gen("guard_rejected", "ok",
                 problems=["angle 1 uses numbers absent from the facts it cites (x): 77%"])]
    assert E.summarise(gens)["problem_kinds"] == {"uncited_number": 1}


def test_summarise_handles_an_empty_run():
    s = E.summarise([])
    assert s["n_generations"] == 0 and s["first_attempt_pass_rate"] is None


# --- fixtures from the serving payload -------------------------------------------------- #
def test_fact_packs_cover_the_whole_horizon_not_just_the_briefed_gameweek():
    """`brief_matches` narrates only the current GW; the harness wants every fixture the
    engine already produced, or there aren't enough packs to measure against."""
    payload = {
        "matches": [dict(MATCH), dict(MATCH, match_id="3-1-2", gw=3)],
        "records": [{"team_id": 1, "web_name": "Striker", "team_name": "Alpha",
                     "position": "FWD", "xp": 6.42, "price": 9.5, "ownership": 31.2}],
    }
    packs = E.fact_packs(payload)
    assert [mid for mid, _ in packs] == ["1-1-2", "3-1-2"]
    assert packs[1][1]["gameweek"] == 3
    assert packs[0][1]["top_players_by_expected_points"][0]["name"] == "Striker"


def test_fact_packs_survive_a_fixture_with_no_scored_players():
    packs = E.fact_packs({"matches": [dict(MATCH)], "records": []})
    assert "top_players_by_expected_points" not in packs[0][1]
