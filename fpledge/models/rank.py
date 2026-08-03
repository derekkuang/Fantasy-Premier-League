"""Rank-relative valuation: effective ownership and differential value.

In FPL your OVERALL RANK is your score minus the field's, so captaincy and differential
decisions should optimise expected RANK, not raw xP. Owning a template player (everyone
has it) barely moves your rank; a low-owned player who returns gains rank. This is the
review's headline point — a raw-xP maximiser optimises the wrong objective.

First cut uses overall ownership (`selected_by_percent`) as an effective-ownership (EO)
proxy. True captain-EO (concentrated on premiums) needs top-manager data — a later
enrichment, documented rather than faked.
"""

from __future__ import annotations


def effective_ownership(ownership_pct: float) -> float:
    """EO as a fraction in [0, 1] from FPL's selected_by_percent (0-100)."""
    return max(0.0, min(ownership_pct / 100.0, 1.0))


def differential_value(xp: float, eo: float) -> float:
    """Expected points gained vs the field by OWNING a player: xp * (1 - eo).

    High for high-xP, low-ownership players — the definition of a good differential.
    """
    return xp * (1.0 - eo)


def template_risk(xp: float, eo: float) -> float:
    """Expected points LOST vs the field by NOT owning a player: xp * eo.

    High for high-xP, high-ownership players — the ones you can't afford to miss.
    """
    return xp * eo


def captain_rank_score(xp: float, eo: float) -> float:
    """Differential-adjusted captain value: 2 * xp * (1 - eo).

    Captaincy doubles a player; against the field, the rank benefit scales with how few
    others captain the same player. Rewards a high-xP pick the field is NOT piling on.

    WARNING: this has no lower bound on xp, so it must NOT be used as a sole selector — an
    unowned low-xP player would win. Always gate candidates through an xP floor first;
    see `differential_captain_index`.
    """
    return 2.0 * xp * (1.0 - eo)


# --- the standardised risk band ---------------------------------------------------- #
# `diff_value` and `template_risk` are in expected-points-vs-the-field, which is the right
# unit for RANKING but a terrible one for reading: "4.48" carries no scale, no direction and
# no sense of whether it is large. This bands the same decision onto 1-5, matching the FDR
# scale the app already teaches (low = safe/conventional, high = volatile/contrarian) so it
# can reuse the existing colour ramp, digit glyph and legend pattern.
#
# It is derived from OWNERSHIP ALONE and is deliberately not a quality score: it says how
# contrarian a pick is, never how good. Quality stays with xP and the xP floor. Thresholds
# are FPL community convention, not fitted — they are fixed rather than pool percentiles so a
# player's band means the same thing from one gameweek to the next.
# KEEP IN SYNC with BAND_RANGE in web/src/lib/risk.ts, which prints these cut points in the
# legend and in every row's tooltip — a mismatch makes the UI state a threshold that isn't
# real. `test_risk_tier_cut_points_match_the_published_ranges` guards the pair.
RISK_TIERS = (
    (30.0, 1, "Template"),      # nearly everyone owns them; not owning is the risk
    (15.0, 2, "Popular"),
    (7.0, 3, "Emerging"),
    (2.0, 4, "Differential"),
    (0.0, 5, "Deep punt"),      # under 2% owned — a genuine swing either way
)


def risk_tier(ownership_pct: float) -> int:
    """Ownership banded 1 (template) .. 5 (deep punt)."""
    for threshold, tier, _ in RISK_TIERS:
        if ownership_pct >= threshold:
            return tier
    return 5


def risk_label(tier: int) -> str:
    """The human name for a risk tier ("Differential")."""
    for _, t, label in RISK_TIERS:
        if t == tier:
            return label
    return ""


def differential_captain_index(xps, eos, alpha: float = 0.8):  # noqa: ANN001
    """Index of the best DIFFERENTIAL captain among parallel xps/eos, subject to an xP floor.

    An unowned LOW-xP player is noise, not a rank play — captaining a 4.5-xP differential
    over a 9-xP template loses rank in expectation. So only players within `alpha` of the
    best available xP qualify; among those, maximise `captain_rank_score` (which then rewards
    lower ownership). Returns None for an empty list.
    """
    if not xps:
        return None
    floor = alpha * max(xps)
    best_i, best_score = None, float("-inf")
    for i, (xp, eo) in enumerate(zip(xps, eos, strict=True)):
        if xp < floor:
            continue
        score = captain_rank_score(xp, eo)
        if score > best_score:
            best_i, best_score = i, score
    return best_i
