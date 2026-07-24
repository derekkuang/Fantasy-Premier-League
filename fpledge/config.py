"""Central configuration: paths, data sources, and the FPL 2025/26 scoring rules.

Scoring constants live here (not hard-coded across modules) so a rules change —
like the 2025/26 defensive-contribution addition — is a one-line edit.
"""

from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths (override the data root with FPLEDGE_DATA_DIR)
# --------------------------------------------------------------------------- #
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("FPLEDGE_DATA_DIR", ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"            # immutable, timestamped landing zone
PROCESSED_DIR = DATA_DIR / "processed"
DUCKDB_PATH = DATA_DIR / "fpledge.duckdb"

# --------------------------------------------------------------------------- #
# Data sources
# --------------------------------------------------------------------------- #
FPL_API_BASE = "https://fantasy.premierleague.com/api"
SEASON = "2025-26"

# Polite scraping/API defaults (the FPL API is unauthenticated but undocumented;
# be a good citizen so you don't get rate-limited mid-season).
HTTP_TIMEOUT = 20
HTTP_USER_AGENT = "fpledge/0.1 (personal research project)"
FPL_API_MIN_INTERVAL_S = 0.7   # min seconds between element-summary calls

# --------------------------------------------------------------------------- #
# FPL position codes (FPL element_type)
# --------------------------------------------------------------------------- #
ELEMENT_TYPE_TO_POS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
POSITIONS = ("GK", "DEF", "MID", "FWD")

# --------------------------------------------------------------------------- #
# FPL scoring — 2025/26
# --------------------------------------------------------------------------- #
APPEARANCE_60_POINTS = 2       # played 60+ minutes
APPEARANCE_SUB_POINTS = 1      # played 1–59 minutes
GOAL_POINTS = {"GK": 6, "DEF": 6, "MID": 5, "FWD": 4}
ASSIST_POINTS = 3
CLEAN_SHEET_POINTS = {"GK": 4, "DEF": 4, "MID": 1, "FWD": 0}  # only if 60+ mins
GOALS_CONCEDED_PER_PENALTY = 2  # -1 per 2 conceded (GK/DEF only)
SAVES_PER_POINT = 3             # +1 per 3 saves (GK)
PENALTY_SAVE_POINTS = 5
PENALTY_MISS_POINTS = -2
YELLOW_CARD_POINTS = -1
RED_CARD_POINTS = -3
OWN_GOAL_POINTS = -2

# NEW for 2025/26 — Defensive Contribution (capped at +DC_POINTS per match).
# Defenders:            10+ CBIT  (clearances + blocks + interceptions + tackles)
# Midfielders/Forwards: 12+ CBIRT (CBIT + ball recoveries)
# Source: premierleague.com "What's new for 2025/26" (verify each season).
DC_POINTS = 2
DC_THRESHOLD_DEF = 10
DC_THRESHOLD_MID_FWD = 12

# --------------------------------------------------------------------------- #
# Match engine defaults
# --------------------------------------------------------------------------- #
MAX_GOALS = 10          # scoreline matrix is (MAX_GOALS+1) x (MAX_GOALS+1)
DIXON_COLES_RHO = -0.03  # low-score dependence; refit from data, this is a prior
