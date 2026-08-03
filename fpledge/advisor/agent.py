"""The advisor loop: model plans, tools compute.

A manual loop rather than the SDK's `tool_runner`, for three reasons that matter here — a hard
iteration ceiling (an unbounded agent loop is an unbounded bill), token accounting accumulated
across every turn so cost is observable per conversation, and a plain call surface that a
scripted stub can drive in tests without an API key.

Cost shape, worth understanding before changing anything: the API is stateless, so each turn
resends the whole conversation. Turn 5 pays for the system prompt, the tool schemas, the
original question, and every prior tool result. That is why `AdvisorTools` returns small
payloads and why the system+tools prefix is cached — it is identical on every turn, so it is
written once and read at a tenth of the price thereafter.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from .tools import TOOL_SCHEMAS, AdvisorTools

MODEL = "claude-sonnet-5"
EFFORT = "medium"          # a tool-selection loop does not need `high`; this is the main dial
MAX_TOKENS = 8000
MAX_ITERATIONS = 8         # ceiling on tool-calling rounds — runaway protection AND cost cap

# Sonnet 5 list price, $ per million tokens. Cache reads bill at ~0.1x input, writes at 1.25x.
PRICE_IN, PRICE_OUT = 3.00, 15.00
PRICE_CACHE_READ, PRICE_CACHE_WRITE = 0.30, 3.75

SYSTEM = """You are an assistant that helps Fantasy Premier League managers decide what to do with their squad.

HOW YOU WORK
You have tools that read the manager's squad and run the projection model. You do not know
anything about this season yourself — prices, form, injuries and fixtures all change weekly, and
your own memory of them is out of date. Everything you say must come from a tool call.

NEVER state a number that a tool did not return to you in this conversation. Not an expected
points figure, not a price, not a fixture difficulty. If you want to make a point the tools
haven't given you a number for, make it in words.

ALWAYS call get_squad before advising on the team, and ALWAYS call simulate_transfers before
recommending a transfer. simulate_transfers is the only thing that knows whether a move is
legal and whether it actually gains points; a move that looks obvious often fails on the budget
or the three-per-club rule.

RESPECTING WHAT THEY ASK FOR
Managers arrive with constraints — keeping a favourite player, refusing a points hit, saving for
a wildcard, avoiding a particular club. Treat those as hard requirements and search within them.
If a constraint makes a good move impossible, say so plainly and give them the best option that
does respect it, rather than overriding them.

If simulate_transfers refuses a move, read the reason and try a different one. Do not report a
refused move as a recommendation.

BEING HONEST
Expected points are a model projection, not a forecast — roughly on par with FPL's own published
numbers, not better than them. Small differences between two players are noise. Say so when the
gap is small, and never present a projection as what will happen.

If the best move is no move, say that. "Your squad is fine, save the transfer" is a real answer
and often the right one.

Keep replies short and concrete. Lead with the recommendation, then the reason."""


def _system_blocks() -> list[dict]:
    """System prompt as a cacheable block.

    Render order is tools -> system -> messages, so a breakpoint on the last system block
    covers the tool schemas too — the entire fixed prefix of every turn.
    """
    return [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}]


def estimate_cost(usage: dict) -> float:
    """Rough $ for one conversation from accumulated usage. For logging and quota tuning."""
    return round(
        usage.get("input_tokens", 0) / 1e6 * PRICE_IN
        + usage.get("output_tokens", 0) / 1e6 * PRICE_OUT
        + usage.get("cache_read_input_tokens", 0) / 1e6 * PRICE_CACHE_READ
        + usage.get("cache_creation_input_tokens", 0) / 1e6 * PRICE_CACHE_WRITE,
        4,
    )


def _run_tool(tools: AdvisorTools, name: str, args: dict) -> tuple[str, bool]:
    """Execute one tool call. Returns (payload, is_error).

    Failures come back as tool results rather than exceptions so the model can read the
    problem and adapt — an exception would end the turn with nothing useful said.
    """
    fn = getattr(tools, name, None)
    if fn is None:
        return json.dumps({"error": f"no tool named {name!r}"}), True
    try:
        return json.dumps(fn(**args), default=str), False
    except TypeError as exc:
        return json.dumps({"error": f"bad arguments for {name}: {exc}"}), True
    except Exception as exc:  # noqa: BLE001 — any tool failure is the model's to recover from
        return json.dumps({"error": f"{name} failed: {exc}"}), True


def advise(
    tools: AdvisorTools,
    message: str,
    history: Sequence[dict] | None = None,
    client=None,
    max_iterations: int = MAX_ITERATIONS,
) -> dict:
    """One turn of conversation with the advisor.

    Returns {reply, messages, tool_calls, usage, cost_usd, stopped_at_limit}. `messages` is the
    full history to pass back in for a follow-up.
    """
    if client is None:
        raise RuntimeError("advise() needs an Anthropic client — this endpoint costs money "
                           "per call and must never be reachable without one")

    messages: list[dict[str, Any]] = [*(history or []), {"role": "user", "content": message}]
    usage = {"input_tokens": 0, "output_tokens": 0,
             "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    calls: list[dict] = []
    reply, stopped_at_limit = "", False

    for _ in range(max_iterations):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_system_blocks(),
            tools=TOOL_SCHEMAS,
            output_config={"effort": EFFORT},
            messages=messages,
        )
        for k in usage:
            usage[k] += getattr(resp.usage, k, 0) or 0

        # A safety decline returns HTTP 200 with empty/partial content — check before reading.
        if getattr(resp, "stop_reason", None) == "refusal":
            reply = "I can't help with that request."
            break

        text = " ".join(b.text for b in resp.content if b.type == "text").strip()
        if resp.stop_reason != "tool_use":
            reply = text
            break

        messages.append({"role": "assistant", "content": resp.content})

        # Parallel tool calls arrive in one response and ALL results must go back in ONE user
        # message — splitting them teaches the model to stop calling tools in parallel.
        results = []
        for block in (b for b in resp.content if b.type == "tool_use"):
            payload, is_error = _run_tool(tools, block.name, dict(block.input))
            calls.append({"tool": block.name, "input": dict(block.input), "error": is_error})
            results.append({
                "type": "tool_result", "tool_use_id": block.id,
                "content": payload, "is_error": is_error,
            })
        messages.append({"role": "user", "content": results})
    else:
        stopped_at_limit = True
        reply = text or ("I ran out of steps working on that. Ask me something narrower — "
                         "for example, name the player you're thinking of selling.")

    return {
        "reply": reply,
        "messages": messages,
        "tool_calls": calls,
        "usage": usage,
        "cost_usd": estimate_cost(usage),
        "stopped_at_limit": stopped_at_limit,
    }
