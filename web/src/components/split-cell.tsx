// The difficulty cell: one coloured number. "Overall" averages attack (chance to score) and
// defence (chance of a clean sheet); the Attack and Defence lenses show one track each. It used
// to show both tracks in every cell by default, 200 badges for five gameweeks, which made the
// grid hard to scan. The two disagree often (they correlate at only ρ ≈ .665), which is why
// the lenses are one tap away and the info note says so.

import { fdrColour, fdrGlyph } from "@/lib/clubs";

export type TickerLens = "overall" | "attack" | "defence";

/* The band takes the full colour at full width: one bold block per fixture is what makes a
   ticker scannable. The digit still prints (never colour alone) in the per-band glyph colour. */
function SoloTrack({ fdr }: { fdr: number }) {
  return (
    <span
      className="flex items-center justify-center py-[5px] text-[13px] font-bold leading-none tabular-nums"
      style={{ background: fdrColour(fdr), color: fdrGlyph(fdr) }}
    >
      {fdr}
    </span>
  );
}

/** The default view's single number: attack and defence difficulty averaged, half up. The two
 *  disagree often (the reason both lenses exist), so the info note says what this one is. */
export function overallFdr(attack: number, defence: number): number {
  return Math.round((attack + defence) / 2);
}

export function SplitCell({
  attack,
  defence,
  lens,
}: {
  attack: number;
  defence: number;
  lens: TickerLens;
}) {
  const fdr = lens === "attack" ? attack : lens === "defence" ? defence : overallFdr(attack, defence);
  return <span className="block"><SoloTrack fdr={fdr} /></span>;
}
