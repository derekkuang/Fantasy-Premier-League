"""A scripted stand-in for the Anthropic client, so the advisor can be exercised without a key.

This is a development affordance, not a demo mode, and the difference matters. It drives the
REAL agent loop and the REAL tools — `get_squad` and `squad_health` actually run, against the
actual serving records — so every number it reports is genuine. What is scripted is only the
prose and the choice of which tools to call.

That makes it useful for exactly two things: proving the loop, the tool layer and the UI work
end to end, and letting the interface be designed before anyone spends money on it. It is
useless for the thing that actually needs testing — whether a language model picks the right
tools and reasons well about the results — and any response it produces is tagged `stub` all
the way to the browser so it can never be mistaken for the real feature.

Enable with FPLEDGE_ADVISOR_STUB=1. Never set that in production.
"""

from __future__ import annotations

import json
from typing import Any


class _Block:
    def __init__(self, **kw: Any) -> None:
        self.__dict__.update(kw)


class _Usage:
    input_tokens = 0
    output_tokens = 0
    cache_read_input_tokens = 0
    cache_creation_input_tokens = 0


class _Response:
    def __init__(self, content: list, stop_reason: str) -> None:
        self.content = content
        self.stop_reason = stop_reason
        self.usage = _Usage()


class StubClient:
    """Mimics `client.messages.create`, one scripted turn at a time.

    Turn 1 asks for the squad and its health — which is what the system prompt tells the real
    model to do before advising on anything. Turn 2 writes a reply out of whatever those tools
    actually returned.
    """

    def __init__(self) -> None:
        self.messages = self
        self.calls = 0

    def create(self, **kw: Any) -> _Response:
        self.calls += 1
        if self.calls == 1:
            return _Response(
                [
                    _Block(type="tool_use", id="stub_1", name="get_squad", input={}),
                    _Block(type="tool_use", id="stub_2", name="squad_health", input={}),
                ],
                "tool_use",
            )

        squad, health = self._last_results(kw.get("messages", []))
        return _Response([_Block(type="text", text=self._reply(squad, health))], "end_turn")

    @staticmethod
    def _last_results(messages: list) -> tuple[dict, dict]:
        """Pull the two tool payloads back out of the conversation the loop just built."""
        out: list[dict] = []
        for m in messages:
            content = m.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    try:
                        out.append(json.loads(block["content"]))
                    except (ValueError, TypeError, KeyError):
                        out.append({})
        while len(out) < 2:
            out.append({})
        return out[0], out[1]

    @staticmethod
    def _reply(squad: dict, health: dict) -> str:
        players = squad.get("players") or []
        xi = [p for p in players if p.get("starting")]
        bench = [p for p in players if not p.get("starting")]
        best = max(xi, key=lambda p: p.get("xp", 0), default=None)
        flags = health.get("flags") or []

        banner = (
            "**Stub reply — the tools ran for real, the words did not.** "
            "Every figure below came from a live tool call; the sentences around them are "
            "scripted, because no model was asked. Set an API key to get real advice."
        )
        lines = [banner, ""]
        if squad.get("projected_points") is not None:
            lines.append(
                f"Your XI projects **{squad['projected_points']} points** this gameweek with "
                f"**{squad.get('captain') or 'nobody'}** as captain, off a squad worth "
                f"£{squad.get('squad_value')}m with £{squad.get('bank')}m in the bank."
            )
        if best:
            lines.append(
                f"The highest projection in your XI is **{best['name']}** "
                f"({best.get('pos')}, {best.get('team')}) at {best.get('xp')} xP."
            )
        if bench:
            names = ", ".join(p["name"] for p in bench[:4])
            lines.append(f"On the bench: {names}.")
        if flags:
            # check_balance emits {level, message}; older shapes used a [level, message] pair.
            def _msg(f: Any) -> str:
                if isinstance(f, dict):
                    return str(f.get("message", f))
                if isinstance(f, (list, tuple)) and len(f) > 1:
                    return str(f[1])
                return str(f)

            lines.append("Squad health flagged: " + "; ".join(_msg(f) for f in flags[:3]) + ".")
        return "\n\n".join(lines)
