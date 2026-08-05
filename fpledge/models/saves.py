"""Expected goalkeeper saves from shots faced, rather than from goals conceded.

WHY THIS EXISTS. The shipped model sets

    x_saves = opp_lambda * 3 * (x_minutes / 90)

i.e. expected saves proportional to expected goals conceded. That is the wrong quantity, and
the error is not a matter of calibration — it is structural. A keeper behind a good defence
gets a high clean-sheet probability and, under this formula, few saves; a keeper behind a bad
one gets the reverse. The two terms move against each other and largely cancel, which flattens
the goalkeeper ranking into near-noise. `eval/fpl_backtest` measured GK as by far the worst
position and named this as the suspected cause.

Save volume actually tracks SHOTS ON TARGET FACED, which is a different quantity: a team can
concede many shots and few goals (a busy keeper behind a leaky-but-lucky defence) or few shots
and several goals. Understat carries the shot outcome per event, so `SavedShot` counts are
directly observable — this module turns them into a rate and an opponent adjustment.

THE STRUCTURE mirrors the match engine deliberately: a league mean scaled by how many saves
this team's keeper is made to face, and by how many the opponent forces. Both factors are
shrunk toward the league mean, because early in a season a team has played two matches and an
unshrunk rate off two matches is noise presented as a tendency.

POINT-IN-TIME is the caller's responsibility. `SavesRates.build` takes whatever per-gameweek
counts it is given and does not know which gameweek is being predicted; the backtest passes
only gameweeks strictly before the one it is scoring. That is the same contract the rest of
the walk-forward runs under.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

# Matches of evidence the league mean is worth. At 4, a team's own rate carries half the weight
# after 4 matches and ~83% after 20 — deliberately slow, since the whole point is to avoid
# reporting a two-match sample as a defensive characteristic.
PRIOR_MATCHES = 4.0

# Fallback when there is no history at all (gameweek 1, or a promoted side in a fresh season).
# The 2024-25 league mean is ~3.3 saves per team per match; this is only ever used before any
# evidence exists and is replaced by the real mean as soon as one match is in.
DEFAULT_LEAGUE_MEAN = 3.3

# League-average goals per team per match, used only to turn the engine's fixture-specific
# `opp_lambda` into a relative opponent factor in `expected_saves_vs_lambda`. Premier League
# scoring has sat near this for a decade; it is a scale constant, not a fitted parameter, and
# the ratio it feeds is insensitive to small errors in it.
DEFAULT_LEAGUE_LAMBDA = 1.45


@dataclass
class TeamSaveCounts:
    """Per-team accumulator: saves the team's keeper faced, and saves it forced from others."""

    faced: float = 0.0        # saves this team's keeper had to make
    forced: float = 0.0       # saves this team forced from the opposing keeper
    matches_faced: int = 0
    matches_forced: int = 0


@dataclass
class SavesRates:
    """League mean plus per-team defensive/offensive save multipliers, all shrunk."""

    league_mean: float = DEFAULT_LEAGUE_MEAN
    league_lambda: float = DEFAULT_LEAGUE_LAMBDA
    _faced: dict = field(default_factory=dict)    # team_id -> shrunk saves faced per match
    _forced: dict = field(default_factory=dict)   # team_id -> shrunk saves forced per match

    @classmethod
    def build(
        cls,
        counts: Mapping[int, TeamSaveCounts],
        prior_matches: float = PRIOR_MATCHES,
    ) -> SavesRates:
        """Shrink each team's per-match rates toward the league mean."""
        total_saves = sum(c.faced for c in counts.values())
        total_matches = sum(c.matches_faced for c in counts.values())
        mean = total_saves / total_matches if total_matches else DEFAULT_LEAGUE_MEAN
        if mean <= 0:
            mean = DEFAULT_LEAGUE_MEAN

        def shrunk(total: float, matches: int) -> float:
            return (total + prior_matches * mean) / (matches + prior_matches)

        return cls(
            league_mean=mean,
            _faced={t: shrunk(c.faced, c.matches_faced) for t, c in counts.items()},
            _forced={t: shrunk(c.forced, c.matches_forced) for t, c in counts.items()},
        )

    def expected_saves(self, team_id: int, opp_id: int, x_minutes: float) -> float:
        """Expected saves for `team_id`'s keeper against `opp_id`, scaled by expected minutes.

        Multiplicative in the same shape as the goals model: the league mean, times how much
        busier than average this keeper is kept, times how much more than average the opponent
        makes keepers work. An unknown team contributes a factor of exactly 1, so a promoted
        side falls back to the league mean rather than to zero — zero would hand every keeper
        facing them an artificially clean projection.
        """
        if self.league_mean <= 0:
            return 0.0
        d = self._faced.get(team_id, self.league_mean) / self.league_mean
        a = self._forced.get(opp_id, self.league_mean) / self.league_mean
        return self.league_mean * d * a * (x_minutes / 90.0)

    def expected_saves_vs_lambda(
        self, team_id: int, opp_lambda: float, x_minutes: float
    ) -> float:
        """As `expected_saves`, but the opponent factor comes from the match engine.

        `expected_saves` knows only the opponent's season-long average; the engine's
        `opp_lambda` is fitted for THIS fixture and carries home advantage and current form.
        The team's own factor still comes from observed saves faced, which is the part the
        engine has no view of at all — it models goals, not shots on target.
        """
        if self.league_mean <= 0 or self.league_lambda <= 0:
            return 0.0
        d = self._faced.get(team_id, self.league_mean) / self.league_mean
        a = opp_lambda / self.league_lambda
        return self.league_mean * d * a * (x_minutes / 90.0)


def accumulate(
    counts: dict,
    home_id: int,
    away_id: int,
    home_keeper_saves: float,
    away_keeper_saves: float,
) -> None:
    """Fold one played match into `counts`.

    `home_keeper_saves` is what the HOME keeper had to make — which is what the AWAY side
    forced. Getting this backwards is silent and survives every plausibility check, so the
    argument names say whose keeper, never whose shots.
    """
    h = counts.setdefault(home_id, TeamSaveCounts())
    a = counts.setdefault(away_id, TeamSaveCounts())
    h.faced += home_keeper_saves
    h.forced += away_keeper_saves
    h.matches_faced += 1
    h.matches_forced += 1
    a.faced += away_keeper_saves
    a.forced += home_keeper_saves
    a.matches_faced += 1
    a.matches_forced += 1


# --- deriving the counts from Understat shot events ------------------------------------- #
# Understat's `result` vocabulary. Only SavedShot is a save: BlockedShot is stopped by an
# outfield player and MissedShots never reached the target, so neither is worth a save point.
SAVE_RESULT = "SavedShot"


def saves_by_match(shots: Sequence[dict]) -> dict:
    """{match_id: {"h": saves the HOME keeper made, "a": saves the AWAY keeper made}}.

    A shot taken by the home side ("side": "h") that the keeper saved is a save by the AWAY
    keeper. The inversion is the whole reason this is a named function with a test.
    """
    out: dict = {}
    for s in shots:
        if s.get("result") != SAVE_RESULT:
            continue
        mid = str(s.get("match_id", ""))
        rec = out.setdefault(mid, {"h": 0, "a": 0})
        rec["a" if s.get("side") == "h" else "h"] += 1
    return out
