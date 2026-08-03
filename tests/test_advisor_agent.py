"""The advisor loop, driven by a scripted client — no API key, no cost.

What's worth testing here is not the model's judgement (untestable) but the harness around it:
that tool calls actually reach the tools, that parallel calls come back correctly, that a tool
failure is handed to the model instead of crashing the turn, that the loop cannot run forever,
and that usage is accumulated so cost is observable.
"""

from __future__ import annotations

import json

import pytest

from fpledge.advisor.agent import MAX_ITERATIONS, advise, estimate_cost
from fpledge.advisor.tools import AdvisorTools
from tests.test_advisor_tools import OWNED, _records


def _tools():
    return AdvisorTools(_records(), OWNED, bank=2.0, free_transfers=1)


class _Block:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _text(t):
    return _Block(type="text", text=t)


def _use(tool_id, name, inp):
    return _Block(type="tool_use", id=tool_id, name=name, input=inp)


class _Resp:
    def __init__(self, content, stop_reason, usage=None):
        self.content = content
        self.stop_reason = stop_reason
        self.usage = _Block(input_tokens=100, output_tokens=50,
                            cache_read_input_tokens=0, cache_creation_input_tokens=0,
                            **(usage or {}))


class _Client:
    """Replays scripted responses and records what it was sent.

    `messages` is SNAPSHOTTED, not stored by reference: `advise` appends to the same list each
    turn, so recording the reference would make every captured turn alias the final state —
    and any assertion about what turn N actually received would silently be an assertion about
    turn N+k instead.
    """

    def __init__(self, *responses):
        self.responses = list(responses)
        self.sent = []
        self.messages = self

    def create(self, **kw):
        self.sent.append({**kw, "messages": list(kw["messages"])})
        return self.responses[min(len(self.sent) - 1, len(self.responses) - 1)]


def test_a_plain_answer_needs_no_tools():
    c = _Client(_Resp([_text("Save your transfer this week.")], "end_turn"))
    out = advise(_tools(), "should I transfer?", client=c)
    assert out["reply"] == "Save your transfer this week."
    assert out["tool_calls"] == []
    assert len(c.sent) == 1


def test_a_tool_call_reaches_the_real_tool_and_the_result_goes_back():
    c = _Client(
        _Resp([_use("t1", "get_squad", {})], "tool_use"),
        _Resp([_text("You have 15 players.")], "end_turn"),
    )
    out = advise(_tools(), "how's my team?", client=c)
    assert out["reply"] == "You have 15 players."
    assert out["tool_calls"][0]["tool"] == "get_squad"

    # the second request carries the tool_result, and it holds real engine output
    results = c.sent[1]["messages"][-1]["content"]
    assert results[0]["type"] == "tool_result" and results[0]["tool_use_id"] == "t1"
    payload = json.loads(results[0]["content"])
    assert len(payload["players"]) == 15 and payload["free_transfers"] == 1


def test_parallel_tool_calls_return_in_a_single_user_message():
    """Splitting parallel results across messages trains the model out of parallel calling."""
    c = _Client(
        _Resp([_use("a", "get_squad", {}),
               _use("b", "search_players", {"position": "MID", "limit": 2})], "tool_use"),
        _Resp([_text("done")], "end_turn"),
    )
    advise(_tools(), "review my midfield", client=c)
    last = c.sent[1]["messages"][-1]
    assert last["role"] == "user"
    assert len(last["content"]) == 2                     # both results, one message
    assert {r["tool_use_id"] for r in last["content"]} == {"a", "b"}


def test_an_illegal_move_comes_back_as_a_refusal_the_model_can_act_on():
    """The tool enforces the rules, so the model gets told why rather than recommending
    something the game would reject."""
    c = _Client(
        _Resp([_use("t1", "simulate_transfers",
                    {"moves": [{"out_id": 24, "in_id": 999}]})], "tool_use"),
        _Resp([_text("That player isn't available.")], "end_turn"),
    )
    advise(_tools(), "get me 999", client=c)
    payload = json.loads(c.sent[1]["messages"][-1]["content"][0]["content"])
    assert payload["legal"] is False and payload["problems"]


def test_a_bad_tool_name_is_reported_not_raised():
    c = _Client(
        _Resp([_use("t1", "delete_everything", {})], "tool_use"),
        _Resp([_text("I can't do that.")], "end_turn"),
    )
    out = advise(_tools(), "hi", client=c)
    result = c.sent[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True
    assert "no tool named" in json.loads(result["content"])["error"]
    assert out["reply"] == "I can't do that."          # the turn survived


def test_bad_arguments_are_reported_not_raised():
    c = _Client(
        _Resp([_use("t1", "get_squad", {"nonsense": 1})], "tool_use"),
        _Resp([_text("ok")], "end_turn"),
    )
    advise(_tools(), "hi", client=c)
    result = c.sent[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True
    assert "bad arguments" in json.loads(result["content"])["error"]


def test_the_loop_cannot_run_forever():
    """An agent that always wants one more tool call is an unbounded bill. The cap is the
    only thing standing between a prompt-injected or confused model and a large invoice."""
    forever = _Resp([_text("thinking"), _use("t", "get_squad", {})], "tool_use")
    c = _Client(forever)
    out = advise(_tools(), "loop please", client=c, max_iterations=3)
    assert len(c.sent) == 3
    assert out["stopped_at_limit"] is True
    assert out["reply"]                                  # still says something useful


def test_usage_accumulates_across_every_turn():
    """Cost is per conversation, not per call — accounting only on the last turn would
    under-report a five-turn conversation by most of its cost."""
    c = _Client(
        _Resp([_use("t1", "get_squad", {})], "tool_use"),
        _Resp([_text("done")], "end_turn"),
    )
    out = advise(_tools(), "hi", client=c)
    assert out["usage"]["input_tokens"] == 200           # 2 turns x 100
    assert out["usage"]["output_tokens"] == 100
    assert out["cost_usd"] > 0


def test_cached_reads_are_priced_far_below_fresh_input():
    fresh = {"input_tokens": 10_000, "output_tokens": 0,
             "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    cached = {"input_tokens": 0, "output_tokens": 0,
              "cache_read_input_tokens": 10_000, "cache_creation_input_tokens": 0}
    assert estimate_cost(cached) < estimate_cost(fresh) / 5


def test_the_prefix_is_cacheable_and_identical_every_turn():
    """The system+tools prefix is resent on every turn; if it isn't byte-identical, nothing
    caches and the conversation costs several times more than it should."""
    c = _Client(
        _Resp([_use("t1", "get_squad", {})], "tool_use"),
        _Resp([_text("done")], "end_turn"),
    )
    advise(_tools(), "hi", client=c)
    first, second = c.sent[0], c.sent[1]
    assert first["system"] == second["system"]
    assert first["tools"] == second["tools"]
    assert first["system"][-1]["cache_control"] == {"type": "ephemeral"}


def test_effort_and_model_are_pinned():
    c = _Client(_Resp([_text("hi")], "end_turn"))
    advise(_tools(), "hi", client=c)
    assert c.sent[0]["model"] == "claude-sonnet-5"
    assert c.sent[0]["output_config"]["effort"] == "medium"


def test_a_refusal_is_handled_before_reading_content():
    """A safety decline returns HTTP 200 with empty content; indexing it would crash."""
    c = _Client(_Resp([], "refusal"))
    out = advise(_tools(), "something disallowed", client=c)
    assert out["reply"] and out["tool_calls"] == []


def test_history_is_returned_for_follow_ups():
    c = _Client(_Resp([_text("first answer")], "end_turn"))
    out = advise(_tools(), "hello", client=c)
    assert out["messages"][0] == {"role": "user", "content": "hello"}

    c2 = _Client(_Resp([_text("second answer")], "end_turn"))
    out2 = advise(_tools(), "and now?", history=out["messages"], client=c2)
    assert [m["content"] for m in c2.sent[0]["messages"]][:2] == ["hello", "and now?"]
    assert out2["reply"] == "second answer"


def test_no_client_is_a_hard_error():
    """This endpoint costs money per call; reaching it without a configured client should be
    loud, never a silent no-op that looks like a working feature."""
    with pytest.raises(RuntimeError, match="costs money"):
        advise(_tools(), "hi", client=None)


def test_default_iteration_cap_is_sane():
    assert 3 <= MAX_ITERATIONS <= 12
