// The difficulty cell. Under the default "overall" lens it shows BOTH tracks — attack
// difficulty on the left, defence difficulty on the right — because the two runs disagree far
// too often to collapse into one number: across a payload they correlate at only ρ ≈ .665 and
// ~52% of cells carry different ratings (Liverpool rank 2nd for attack but 12th for defence;
// Everton the reverse). Picking the attack or defence lens narrows every cell to just that
// track, so the grid reads as a single clean ranking when you already know what you're
// shopping for.

import { fdrColour, fdrGlyph } from "@/lib/clubs";

export type TickerLens = "overall" | "attack" | "defence";

/* One letter per track. black/55 not /45: as 8px TEXT this needs 4.5:1, not the 3:1 a
   decorative mark needed — /45 measures 3.35:1 on white and fails. */
const Tag = ({ attack }: { attack: boolean }) => (
  <span className="flex-none text-[8px] font-bold text-black/55 dark:text-white/55">
    {attack ? "A" : "D"}
  </span>
);

/* The glyph colour is per-band (fdrGlyph), never a blanket white — two of the five FDR
   hexes cannot carry a small white digit at AA. */
const Digit = ({ fdr }: { fdr: number }) => (
  <span
    className="grid h-[13px] min-w-[13px] place-items-center rounded-[3px] text-[9px] font-bold tabular-nums"
    style={{ background: fdrColour(fdr), color: fdrGlyph(fdr) }}
  >
    {fdr}
  </span>
);

/* Side by side, each track needs its A/D letter to say which is which — a 14% tint keeps two
   colours in one small tile from fighting. */
function Half({ fdr, attack }: { fdr: number; attack: boolean }) {
  return (
    <span
      className="flex items-center justify-center gap-1 py-1"
      style={{ background: `color-mix(in oklab, ${fdrColour(fdr)} 14%, transparent)` }}
    >
      <Tag attack={attack} />
      <Digit fdr={fdr} />
    </span>
  );
}

/* Alone, there is nothing to disambiguate — the active pill and the legend already say which
   track this is — so the letter goes and the band takes the full colour at full width. Reads
   as one bold block per fixture, which is what makes a ticker scannable. The digit still
   prints (never colour alone) in the per-band glyph colour. */
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

export function SplitCell({
  attack,
  defence,
  lens,
}: {
  attack: number;
  defence: number;
  lens: TickerLens;
}) {
  if (lens === "attack") return <span className="block"><SoloTrack fdr={attack} /></span>;
  if (lens === "defence") return <span className="block"><SoloTrack fdr={defence} /></span>;

  return (
    <span className="grid grid-cols-2 gap-px">
      <Half fdr={attack} attack />
      <Half fdr={defence} attack={false} />
    </span>
  );
}
