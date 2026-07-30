"""FastAPI serving layer over the fpledge engine (Phase 0 of the full-stack pivot).

Design: the expensive engine fit runs ONCE in a precompute job (`api.precompute`), which
writes a self-contained JSON artifact per gameweek to a serving store (`api.store`). The
API (`api.main`) only ever READS that store and does the cheap per-user personalisation
(join a manager's 15, run the transfer suggester / balance check). Reads stay instant and
cost stays flat as users grow. The engine code is reused UNCHANGED.
"""

from __future__ import annotations

MODEL_VER = "structured-0.1"  # tag every serving artifact; bump when the xP model changes
