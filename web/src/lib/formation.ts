// Pure helpers for the interactive XI: legal formation checks, captain selection under
// each basis, and projected-points maths. Kept framework-free so the logic is easy to
// reason about (and mirrors the backend's optimizer/rank rules).

import type { SquadPlayer } from "@/lib/api";

export type Pos = "GK" | "DEF" | "MID" | "FWD";
export const POS_ORDER: Pos[] = ["GK", "DEF", "MID", "FWD"];

// XI formation bounds (must total 11): 1 GK, 3-5 DEF, 2-5 MID, 1-3 FWD.
const BOUNDS: Record<Pos, [number, number]> = { GK: [1, 1], DEF: [3, 5], MID: [2, 5], FWD: [1, 3] };

export function countByPos(players: SquadPlayer[]): Record<Pos, number> {
  const c: Record<Pos, number> = { GK: 0, DEF: 0, MID: 0, FWD: 0 };
  for (const p of players) c[p.position]++;
  return c;
}

export function formationLabel(starters: SquadPlayer[]): string {
  const c = countByPos(starters);
  return `${c.DEF}-${c.MID}-${c.FWD}`;
}

/** After replacing a starter at `outPos` with a bench player at `inPos`, is the XI legal? */
export function swapLegal(counts: Record<Pos, number>, outPos: Pos, inPos: Pos): boolean {
  if (outPos === inPos) return true; // straight same-position swap never breaks the shape
  const c = { ...counts, [outPos]: counts[outPos] - 1, [inPos]: counts[inPos] + 1 };
  return POS_ORDER.every((p) => c[p] >= BOUNDS[p][0] && c[p] <= BOUNDS[p][1]);
}

const capScore = (p: SquadPlayer) =>
  p.captain_score ?? 2 * p.xp * (1 - (p.ownership ?? 0) / 100);

/**
 * Captain for the current XI under the chosen basis.
 * - "xp": highest raw xP.
 * - "rank": among starters within `alpha` of the best xP (the xP floor), the highest
 *   differential captain score 2·xP·(1−EO). Mirrors rank.differential_captain_index.
 */
export function chooseCaptainId(
  starters: SquadPlayer[],
  basis: "rank" | "xp",
  alpha = 0.8,
): number | null {
  if (starters.length === 0) return null;
  if (basis === "xp") {
    return starters.reduce((a, b) => (b.xp > a.xp ? b : a)).element_id;
  }
  const floor = alpha * Math.max(...starters.map((p) => p.xp));
  const eligible = starters.filter((p) => p.xp >= floor);
  const pool = eligible.length ? eligible : starters;
  return pool.reduce((a, b) => (capScore(b) > capScore(a) ? b : a)).element_id;
}

export function xpFloor(starters: SquadPlayer[], alpha = 0.8): number {
  return starters.length ? alpha * Math.max(...starters.map((p) => p.xp)) : 0;
}

/** Projected GW points = XI xP + the captain's xP again (captain doubled). */
export function projectedPoints(starters: SquadPlayer[], captainId: number | null): number {
  const xi = starters.reduce((s, p) => s + p.xp, 0);
  const cap = starters.find((p) => p.element_id === captainId);
  return xi + (cap ? cap.xp : 0);
}
