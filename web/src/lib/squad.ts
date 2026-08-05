// Building a squad by hand, rather than fetching one from an FPL entry id.
//
// The dashboard already does all of its own maths in the browser — projected points, the
// captain, squad health and the swap deltas are all recomputed client-side so the XI can be
// edited without a round trip. That means a squad the user assembles here can drive exactly
// the same view as a real one, with no backend involvement: `/predictions` already returns a
// superset of what a squad row needs, so a pick is a Prediction plus two booleans.
//
// The one thing that genuinely can't be reproduced is `best_transfer`. It is computed by the
// backend against a player pool and a bank, and a squad you just invented has neither a prior
// squad nor a transfer history to move from. The dashboard hides that card for a manual squad
// rather than showing a suggestion that means nothing.

import type { Prediction, SquadPlayer, TeamResponse } from "@/lib/api";
import { countByPos, type Pos } from "@/lib/formation";

export const BUDGET = 100.0;
export const MAX_PER_CLUB = 3;
export const SQUAD_QUOTA: Record<Pos, number> = { GK: 2, DEF: 5, MID: 5, FWD: 3 };
export const SQUAD_SIZE = 15;

/** The eight legal XI shapes: 1 GK plus ten outfield inside 3–5 / 2–5 / 1–3. */
export const FORMATIONS: [number, number, number][] = (() => {
  const out: [number, number, number][] = [];
  for (let d = 3; d <= 5; d++)
    for (let m = 2; m <= 5; m++)
      for (let f = 1; f <= 3; f++) if (d + m + f === 10) out.push([d, m, f]);
  return out;
})();

// --- share codes ---------------------------------------------------------------------- //
// Fixed-width base36 so the code is delimiter-free and fixed length: 15 ids × 3 chars = 45
// characters, which fits in a URL, a text message, and a Reddit comment without wrapping.

export function encodeSquad(ids: number[]): string {
  return ids.map((id) => id.toString(36).padStart(3, "0")).join("");
}

export function decodeSquad(code: string | null | undefined): number[] {
  if (!code || code.length % 3 !== 0) return [];
  const out: number[] = [];
  for (let i = 0; i < code.length; i += 3) {
    const n = parseInt(code.slice(i, i + 3), 36);
    if (!Number.isFinite(n) || n <= 0) return [];
    out.push(n);
  }
  return out;
}

// --- rules ---------------------------------------------------------------------------- //
export type Violation = { rule: string; detail: string };

export function clubCounts(picks: Prediction[]): Map<string, number> {
  const m = new Map<string, number>();
  for (const p of picks) m.set(p.team ?? "?", (m.get(p.team ?? "?") ?? 0) + 1);
  return m;
}

export function totalCost(picks: Prediction[]): number {
  return Math.round(picks.reduce((s, p) => s + p.price, 0) * 10) / 10;
}

/** Every rule the squad currently breaks. Empty means it is a legal FPL squad. */
export function violations(picks: Prediction[]): Violation[] {
  const out: Violation[] = [];
  const cost = totalCost(picks);
  if (cost > BUDGET)
    out.push({ rule: "Over budget", detail: `£${cost.toFixed(1)}m of £${BUDGET.toFixed(1)}m` });

  const counts = countByPos(picks as unknown as SquadPlayer[]);
  for (const pos of ["GK", "DEF", "MID", "FWD"] as Pos[]) {
    if (counts[pos] > SQUAD_QUOTA[pos])
      out.push({ rule: `Too many ${pos}`, detail: `${counts[pos]} of ${SQUAD_QUOTA[pos]}` });
  }

  for (const [club, n] of clubCounts(picks)) {
    if (n > MAX_PER_CLUB)
      out.push({ rule: "Club limit", detail: `${n} from ${club} — max ${MAX_PER_CLUB}` });
  }
  return out;
}

/** Why this player can't be added right now — or null if they can. Checked before the tap,
 *  so a blocked pick explains itself instead of silently doing nothing. */
export function blockedReason(p: Prediction, picks: Prediction[]): string | null {
  if (picks.some((q) => q.element_id === p.element_id)) return "already picked";
  const counts = countByPos(picks as unknown as SquadPlayer[]);
  if (counts[p.position] >= SQUAD_QUOTA[p.position])
    return `${p.position} full (${SQUAD_QUOTA[p.position]})`;
  if ((clubCounts(picks).get(p.team ?? "?") ?? 0) >= MAX_PER_CLUB)
    return `3 from ${p.team} already`;
  if (totalCost(picks) + p.price > BUDGET + 1e-9) return "over budget";
  return null;
}

// --- the starting XI ------------------------------------------------------------------ //
/** Highest-xP legal XI, by trying all eight shapes. Mirrors the backend's best_xi. */
export function bestXI(squad: SquadPlayer[]): Set<number> {
  const by = (pos: Pos) =>
    squad.filter((p) => p.position === pos).sort((a, b) => b.xp - a.xp);
  const gks = by("GK");
  const defs = by("DEF");
  const mids = by("MID");
  const fwds = by("FWD");
  if (!gks.length) return new Set();

  let best: SquadPlayer[] = [];
  let bestXp = -Infinity;
  for (const [d, m, f] of FORMATIONS) {
    if (defs.length < d || mids.length < m || fwds.length < f) continue;
    const xi = [gks[0], ...defs.slice(0, d), ...mids.slice(0, m), ...fwds.slice(0, f)];
    const xp = xi.reduce((s, p) => s + p.xp, 0);
    if (xp > bestXp) {
      bestXp = xp;
      best = xi;
    }
  }
  return new Set(best.map((p) => p.element_id));
}

// --- auto-pick ------------------------------------------------------------------------ //
/** A legal starting squad, so nobody faces fifteen empty slots and gives up.
 *
 *  Deliberately a heuristic, not the optimiser: take players in xP order, but only when the
 *  cheapest possible filling of every REMAINING slot still fits in what's left. Pure greed by
 *  xP spends the budget on three premiums and then cannot afford a goalkeeper. This lands a
 *  legal, sensible squad to edit from — the honest framing is "a starting point", and the UI
 *  says so rather than implying it is optimal. */
export function autoPick(pool: Prediction[]): Prediction[] {
  const usable = pool.filter((p) => !p.low_coverage && p.price > 0);
  const cheapest: Record<Pos, number[]> = { GK: [], DEF: [], MID: [], FWD: [] };
  for (const pos of ["GK", "DEF", "MID", "FWD"] as Pos[]) {
    cheapest[pos] = usable
      .filter((p) => p.position === pos)
      .map((p) => p.price)
      .sort((a, b) => a - b);
  }

  const picks: Prediction[] = [];
  const need = (): Record<Pos, number> => {
    const c = countByPos(picks as unknown as SquadPlayer[]);
    return { GK: SQUAD_QUOTA.GK - c.GK, DEF: SQUAD_QUOTA.DEF - c.DEF, MID: SQUAD_QUOTA.MID - c.MID, FWD: SQUAD_QUOTA.FWD - c.FWD };
  };
  // Floor price of filling everything still outstanding, ignoring the club rule — an
  // underestimate, which is what we want: it never wrongly rejects an affordable player.
  const floorCost = (n: Record<Pos, number>, skip: Pos | null) => {
    let sum = 0;
    for (const pos of ["GK", "DEF", "MID", "FWD"] as Pos[]) {
      const k = n[pos] - (skip === pos ? 1 : 0);
      for (let i = 0; i < k; i++) sum += cheapest[pos][i] ?? 0;
    }
    return sum;
  };

  for (const p of [...usable].sort((a, b) => b.xp - a.xp)) {
    if (picks.length >= SQUAD_SIZE) break;
    const n = need();
    if (n[p.position] <= 0) continue;
    if ((clubCounts(picks).get(p.team ?? "?") ?? 0) >= MAX_PER_CLUB) continue;
    if (totalCost(picks) + p.price + floorCost(n, p.position) > BUDGET + 1e-9) continue;
    picks.push(p);
  }
  return picks;
}

// --- adapting to the dashboard --------------------------------------------------------- //
/** A Prediction is a squad row plus two booleans. */
export function toSquadPlayer(p: Prediction, isStarter: boolean, isCaptain: boolean): SquadPlayer {
  return { ...p, is_starter: isStarter, is_captain: isCaptain };
}

/** The payload the dashboard expects, assembled locally.
 *
 *  `entry_id: 0` is not a real entry and nothing downstream treats it as one — the dashboard
 *  is told explicitly that this squad is manual, rather than inferring it from a magic id. */
export function buildTeamResponse(picks: Prediction[], gw: number, meta: TeamResponse["meta"]): TeamResponse {
  const provisional = picks.map((p) => toSquadPlayer(p, false, false));
  const starters = bestXI(provisional);
  const squad = picks.map((p) => toSquadPlayer(p, starters.has(p.element_id), false));
  const xi = squad.filter((p) => p.is_starter);
  const captain = xi.length ? xi.reduce((a, b) => (b.xp > a.xp ? b : a)) : null;
  if (captain) captain.is_captain = true;

  return {
    meta,
    entry_id: 0,
    gw,
    bank: Math.round((BUDGET - totalCost(picks)) * 10) / 10,
    free_transfers: 0,
    projected_points: null,   // the dashboard recomputes this from the live XI
    captain: captain ? { element_id: captain.element_id, web_name: captain.web_name, xp: captain.xp } : null,
    squad,
    best_transfer: null,      // needs a server-side pool + a real bank; see the header note
    balance: null,
    unscored_elements: [],
  };
}
