"""Squad advisor: a tool-using agent over the existing engine.

`suggest_transfers` already computes the single best move by net xP. What it cannot express is
a constraint — "keep Haaland", "no hits this week", "I'm saving for a wildcard", "not a third
Arsenal player". Supporting those in the optimiser means a new parameter per constraint,
forever; the space of things a manager might say is open-ended, while the space of operations
is small and fixed. That asymmetry is what an agent is for.

The division of labour is strict: the model plans and searches, the tools compute. Every
number it reports came out of `AdvisorTools`, which is the same engine behind the rest of the
site — so it cannot fabricate an expected-points figure any more than it can fabricate a
league table.
"""

from .tools import TOOL_SCHEMAS, AdvisorTools

__all__ = ["TOOL_SCHEMAS", "AdvisorTools"]
