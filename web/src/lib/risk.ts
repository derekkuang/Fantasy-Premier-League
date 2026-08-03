// The risk band: ownership banded 1 (Template) .. 5 (Deep punt), as shipped by the API in
// `risk_tier` / `risk_label`. Never derive it here — the API is the source of truth.
//
// WHY THIS IS NOT `fdrColour`. That ramp runs green (1) -> red (5), and on the Fixtures page
// green means "easy fixture, good". Reusing it would paint band 5 red — reading as "bad
// player" — when a deep punt is the exact archetype this page exists to surface. The
// direction is right (low = comfortable) but the connotation is inverted: on Fixtures, 5 is
// something to avoid; here, 5 is the point.
//
// So the ramp runs neutral -> deep emerald. Band 1 carries no accent at all (the whole field
// owns him; there is no signal), and intensity rises with how contrarian the pick is.

export const BAND_STYLE: Record<number, { bg: string; fg: string; border: string }> = {
  1: { bg: "var(--chip)",         fg: "var(--fg)",       border: "var(--b10)" },          // neutral
  2: { bg: "var(--band2-bg)",     fg: "var(--band2-fg)", border: "rgba(5,150,105,.35)" }, // emerald tint
  3: { bg: "#0f766e",             fg: "#ffffff",         border: "#0f766e" },             // teal-700    4.9:1
  4: { bg: "#047857",             fg: "#ffffff",         border: "#047857" },             // emerald-700 5.1:1
  5: { bg: "var(--emerald-deep)", fg: "#ffffff",         border: "var(--emerald-deep)" }, // emerald-800 7.0:1
};

// These are printed as copy in the legend and in every row's tooltip, so they must match the
// cut points in fpledge/models/rank.py::RISK_TIERS. That pairing is guarded by
// test_risk_tier_cut_points_match_the_published_ranges — if it fails, change both or neither.
export const BAND_RANGE: Record<number, string> = {
  1: "30%+", 2: "15–30%", 3: "7–15%", 4: "2–7%", 5: "under 2%",
};

export const BAND_BLURB: Record<number, string> = {
  1: "the field already owns him, so he barely moves your rank either way",
  2: "widely owned; owning him keeps pace rather than gaining ground",
  3: "gaining traction — still early enough to be worth something",
  4: "genuinely contrarian; a return here moves your rank",
  5: "almost nobody owns him, so the swing is largest in both directions",
};

/** Fallback to band 3's neutral-ish styling for an unexpected tier rather than crashing. */
export function bandStyle(tier: number) {
  return BAND_STYLE[tier] ?? BAND_STYLE[3];
}

/** The tooltip every band chip carries — the digit and label are never colour alone. */
export function bandTitle(tier: number, label: string): string {
  return `Risk band ${tier} of 5 — ${label}, ${BAND_RANGE[tier] ?? "?"} owned. ` +
    "Derived from ownership alone, not from quality.";
}
