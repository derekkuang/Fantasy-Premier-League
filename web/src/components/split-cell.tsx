// The fixture cell: one coloured number, chosen by the lens.
//
// Overall is difficulty, 1 (easy) to 5 (hard): attack (chance to score) and defence (chance of a
// clean sheet) averaged. The other lenses print the chance itself (HANDOFF §40): Win % is the
// match's win probability, Goals the expected goals, Clean sheet the chance of keeping one. Goals
// and Clean sheet keep the attack and defence difficulty colours, so a colour means what it always
// meant; Win % is banded onto the same scale. It used to show both difficulty tracks in every
// cell, 200 badges for five gameweeks, which made the grid hard to scan.

import type { TickerFixture } from "@/lib/api";
import { fdrColour, fdrGlyph } from "@/lib/clubs";
import { pct, winBand, type FixtureOdds } from "@/lib/odds";

export type TickerLens = "overall" | "win" | "goals" | "cs";

/** The default view's single number: attack and defence difficulty averaged, half up. The two
 *  disagree often (they correlate at only ρ ≈ .665), which is why the other lenses exist. */
export function overallFdr(attack: number, defence: number): number {
  return Math.round((attack + defence) / 2);
}

/** The colour band and the text a cell shows under a lens; null when the odds are missing. */
export function cellValue(f: TickerFixture, odds: FixtureOdds | undefined, lens: TickerLens): { band: number; text: string } | null {
  switch (lens) {
    case "overall": { const b = overallFdr(f.attack_fdr, f.defence_fdr); return { band: b, text: String(b) }; }
    case "goals": return { band: f.attack_fdr, text: f.lam_for.toFixed(1) };
    case "win": return odds ? { band: winBand(odds.win), text: pct(odds.win) } : null;
    case "cs": return odds ? { band: f.defence_fdr, text: pct(odds.cs) } : null;
  }
}

/* The band takes the full colour at full width: one bold block per fixture is what makes a
   ticker scannable. The text always prints (never colour alone) in the band's glyph colour. */
export function SplitCell({ fixture, odds, lens }: { fixture: TickerFixture; odds?: FixtureOdds; lens: TickerLens }) {
  const v = cellValue(fixture, odds, lens);
  if (!v) {
    return <span className="block py-[5px] text-center text-[13px] leading-none text-muted">–</span>;
  }
  return (
    <span
      className="block py-[5px] text-center text-[13px] font-bold leading-none tabular-nums"
      style={{ background: fdrColour(v.band), color: fdrGlyph(v.band) }}
    >
      {v.text}
    </span>
  );
}
