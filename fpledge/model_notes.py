"""The written half of the model page: what we tried, what the model doesn't know, and how it works.

These used to live in `scripts/build_model_card.py` and be frozen into the card artifact the day
the card was built, so the page kept saying things that stopped being true (market odds
"dormant in preseason" weeks after they went live). The measured numbers still come from the
card; these notes come from here, so `/model` serves the current text on every deploy.
Plain language: this is read by FPL managers, not by whoever maintains the code.
"""

from __future__ import annotations

EXPERIMENTS = [
    {
        "name": "Recency-weighted minutes",
        "question": "Should recent appearances count more than a season-long average when predicting minutes?",
        "delta": "+0.064 ranking score, all players (0.669 → 0.733)",
        "verdict": "kept",
        "measured": "2026-07-26",
    },
    {
        "name": "Recency-weighted goals and assists",
        "question": "The same idea, applied to attacking rates instead of minutes.",
        "delta": "+0.002 ranking score",
        "verdict": "null — attacking form is not the gap",
        "measured": "2026-07-26",
    },
    {
        "name": "Bonus from goal and assist involvement",
        "question": "Estimate bonus from involvement in goals rather than a flat rate.",
        "delta": "+0.002 ranking score",
        "verdict": "null",
        "measured": "2026-07-27",
    },
    {
        "name": "A machine-learned points model",
        "question": "Can a gradient-boosted model predict single-gameweek points better than the structured one?",
        "delta": "structured 0.320 against 0.277 and 0.244 for the two learned versions",
        "verdict": "rejected — single-gameweek points are too noisy and the public data too thin, "
                   "so the learned model fits the noise",
        "measured": "2026-07-27",
    },
    {
        "name": "Goals-conceded penalty for goalkeepers and defenders",
        "question": "Does modelling the −1 for every two goals conceded help?",
        "delta": "+0.009 ranking score",
        "verdict": "kept",
        "measured": "2026-07-30",
    },
    {
        "name": "Bookmaker odds for expected goals",
        "question": "Use the betting market's view of each match, with the bookmaker margin removed.",
        "delta": "+0.0085 ranking score",
        "verdict": "kept — used for every match bookmakers have priced",
        "measured": "2026-07-31",
    },
    {
        "name": "Team strengths learn from this season",
        "question": "Should the match model learn from this season's results as well as past seasons'?",
        "delta": "match log loss 0.992 → 0.970 on 1,900 held-out matches (bookmakers: 0.952)",
        "verdict": "kept — live from 11 November 2026",
        "measured": "2026-11-04",
    },
    {
        "name": "Player rates update during the season",
        "question": "Should goal, assist, defensive and bonus rates blend in this season's games "
                    "instead of staying at last season's?",
        "delta": "+0.022 ranking score, held out on 2026-27 gameweeks 2–10",
        "verdict": "kept — live from 14 November 2026",
        "measured": "2026-11-13",
    },
    {
        "name": "Recent games count more",
        "question": "Within this season, should the last few games weigh more than earlier ones?",
        "delta": "+0.0005 ranking score, within noise",
        "verdict": "null — recent form adds nothing",
        "measured": "2026-11-13",
    },
]

NOT_MODELLED: dict[str, str] = {
    "Price changes": (
        "There is no price-change forecast. The site shows how prices have moved, never how "
        "they will."
    ),
    "Who captains whom": (
        "Ownership is the share of all managers who own a player, not how many captain him. "
        "Every ownership figure on the site inherits that."
    ),
    "Chip timing": "Wildcard, Bench Boost, Triple Captain and Free Hit are not simulated.",
    "Planning several weeks ahead": (
        "The squad optimiser maximises one gameweek. It won't tell you to take a worse week "
        "now for a better run later."
    ),
    "Bench order and auto-subs": (
        "The bench is ranked, but auto-substitution is not simulated, so a projection assumes "
        "your starting XI plays."
    ),
    "Clubs with little history": (
        "A club with too little playing time on record, usually a promoted one early in the "
        "season, gets a cautious default instead of estimated attacking shares, and stays out "
        "of the low-owned rankings until enough minutes are in."
    ),
    "Team news beyond FPL's flags": (
        "Availability comes from FPL's own status. A press-conference hint that FPL hasn't "
        "published yet hasn't reached this model either."
    ),
    "Where a team attacks": (
        "Shot locations and defensive duels need professional-grade event data, which this "
        "site doesn't have."
    ),
}

METHOD = {
    "match model": "A Dixon-Coles model fitted to four seasons of results, this one included, with "
                   "older matches counting less. It gives every fixture a full table of scoreline "
                   "chances; clean sheets and difficulty ratings are read from it. Where "
                   "bookmakers price a match, their odds set the expected goals instead.",
    "expected points": "Each way of scoring is worked out separately (playing time, goals, "
                       "assists, clean sheets, saves, defensive contributions, bonus) and the "
                       "parts add up to the total. That is why every projection can be opened "
                       "and read line by line.",
    "player rates": "A player's goal, assist, defensive and bonus rates blend last season with "
                    "this one; last season counts as three full games, so this season takes "
                    "over as the games pile up. New signings start from their position's average.",
    "ranking score": "How well the predicted order of players matched the order they actually "
                     "scored in, gameweek by gameweek (Spearman rank correlation; 1 is perfect). "
                     "Picking a squad is a ranking problem, so this is the number that matters most.",
    "the comparison": "This season, against FPL's own forecast as it stood before each deadline, "
                      "captured by this site, on the same players. Last season's test used the "
                      "community dataset's copy of FPL's forecast, shifted to what a manager "
                      "could see before the deadline.",
}


def notes() -> dict:
    """The three written sections, in the shape the model card has always carried them."""
    return {
        "experiments": EXPERIMENTS,
        "not_modelled": [{"topic": t, "detail": d} for t, d in NOT_MODELLED.items()],
        "method": METHOD,
    }
