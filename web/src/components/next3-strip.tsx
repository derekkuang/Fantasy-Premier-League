// The next three gameweeks in the desktop Players table: opponent (home in capitals, away in
// lower case) and that gameweek's projection, on a tint of the fixture's difficulty colour. The
// difficulty digit stays, small, so colour is never the only signal.

import type { PredictionFixture } from "@/lib/api";
import { fdrColour, fdrGlyph } from "@/lib/clubs";
import { oppLabel } from "@/components/season-history";

export function Next3Strip({ fixtures }: { fixtures: PredictionFixture[] }) {
  return (
    <div className="flex items-center gap-1">
      {(fixtures ?? []).slice(0, 3).map((f) => {
        const c = fdrColour(f.fdr);
        return (
          <span
            key={`${f.gw}-${f.opp}`}
            title={`GW${f.gw} v ${f.opp} (${f.home ? "home" : "away"}), difficulty ${f.fdr} of 5`}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-[7px] px-1.5 py-1"
            style={{ background: `color-mix(in oklab, ${c} 16%, transparent)` }}
          >
            <span className="font-mono text-[12px] font-semibold">{oppLabel(f.opp, f.home)}</span>
            <span
              className="grid h-4 min-w-4 place-items-center rounded-[4px] px-0.5 text-[10px] font-bold tabular-nums"
              style={{ background: c, color: fdrGlyph(f.fdr) }}
            >
              {f.fdr}
            </span>
            <span className="text-[13px] font-semibold tabular-nums">{f.xp.toFixed(1)}</span>
          </span>
        );
      })}
    </div>
  );
}
