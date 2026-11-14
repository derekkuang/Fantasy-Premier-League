// Match odds on the fixtures grid and the match page (HANDOFF §40).
//
// The fixtures grid gets its numbers from the ticker; the win and clean-sheet chances live on
// the matches payload, so the page joins the two by gameweek and the two clubs. Kept small:
// the client only ever receives one entry per club per fixture.

import type { Match } from "@/lib/api";

export type FixtureOdds = { id: string; win: number; cs: number };

/** "gw:team:opponent", from the team's side. */
export const oddsKey = (gw: number, teamId: number, oppId: number) => `${gw}:${teamId}:${oppId}`;

export function oddsByFixture(matches: Match[]): Record<string, FixtureOdds> {
  const out: Record<string, FixtureOdds> = {};
  for (const m of matches) {
    out[oddsKey(m.gw, m.home_id, m.away_id)] = { id: m.match_id, win: m.result.home_win, cs: m.clean_sheet.home };
    out[oddsKey(m.gw, m.away_id, m.home_id)] = { id: m.match_id, win: m.result.away_win, cs: m.clean_sheet.away };
  }
  return out;
}

/** Win chance on the same 1 (good) to 5 (bad) colour scale as difficulty. */
export function winBand(p: number): number {
  return p >= 0.6 ? 1 : p >= 0.45 ? 2 : p >= 0.3 ? 3 : p >= 0.18 ? 4 : 5;
}

export const pct = (p: number) => `${Math.round(p * 100)}%`;

/** What a player's recent starts say, in a word. Measured over GW6-10 of 2026-27 (see
 *  fpledge/lineup.py): of players who had started all of their club's last five, 91% started
 *  the next match; four of five, 64%; one to three, 29-51%; none, 4%. Fewer than three
 *  matches is too little to say anything. */
export function roleOf(starts: [number, number] | null | undefined): { word: string; tone: "good" | "mid" | "bad" } | null {
  if (!starts) return null;
  const [k, n] = starts;
  if (n < 3) return null;
  if (k === n) return { word: "Nailed", tone: "good" };
  if (k === n - 1) return { word: "Regular", tone: "good" };
  if (k > 0) return { word: "Rotation", tone: "mid" };
  return { word: "No starts", tone: "bad" };
}
