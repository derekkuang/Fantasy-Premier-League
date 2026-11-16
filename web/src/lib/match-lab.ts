// Small helpers the Match Lab pages share (docs/MATCH_LAB.md). Pure functions only.

import type { Match, Prediction } from "@/lib/api";

/** "Sat 21 Nov, 12:30" in UK time. A fixed zone keeps the server and browser render identical. */
export function kickoffLabel(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const day = new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "Europe/London" }).format(d);
  const time = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/London" }).format(d);
  return `${day}, ${time}`;
}

/** The larger gap between our engine and the bookmakers in expected goals, or null if unpriced. */
export function modelGap(m: Match): number | null {
  if (m.source !== "market" || !m.model) return null;
  return Math.max(Math.abs(m.model.lam_home - m.lam_home), Math.abs(m.model.lam_away - m.lam_away));
}

/** A gap this size or more is called a disagreement on the hub. */
export const DISAGREE = 0.3;

/** P(at least one) from an expected count, assuming a Poisson count: our model's chance. */
export function atLeastOne(expected: number): number {
  return 1 - Math.exp(-Math.max(expected, 0));
}

/** FPL's flags that matter for a match: injured, suspended or doubtful. "Unavailable" (u) is how
 *  FPL marks a player loaned out or gone for good, who is never in the reckoning, and "not in
 *  squad" (n) likewise; counting them made one club "22 flagged". Same rule as the News page. */
const MATCH_FLAGS = new Set(["d", "i", "s"]);
export function isFlagged(p: Pick<Prediction, "availability">): boolean {
  const a = p.availability;
  return MATCH_FLAGS.has(a.status ?? "") || (a.status === "a" && a.chance != null && a.chance < 100);
}

/** Highest expected points under this ownership counts as a differential. */
export const DIFFERENTIAL_OWNERSHIP = 10;
