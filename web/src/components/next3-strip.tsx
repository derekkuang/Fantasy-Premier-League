// The next-3-gameweek strip: three cells, each carrying the opponent code, a true-FDR chip
// (digit never conveyed by colour alone), and that GW's xP. A 12% tint of the FDR colour
// makes a good run readable at a glance. `chip` = mobile (34px cells), `row` = desktop table.

import type { PredictionFixture } from "@/lib/api";
import { fdrColour, getClub } from "@/lib/clubs";

export function Next3Strip({
  fixtures,
  variant = "row",
}: {
  fixtures: PredictionFixture[];
  position?: string;
  variant?: "chip" | "row";
}) {
  const cells = (fixtures ?? []).slice(0, 3);

  if (variant === "chip") {
    return (
      <div className="flex flex-none items-center gap-[3px]">
        {cells.map((f) => {
          const c = fdrColour(f.fdr);
          return (
            <span
              key={f.gw}
              title={`GW${f.gw} vs ${f.opp} (${f.home ? "H" : "A"}) — FDR ${f.fdr} · ${f.xp.toFixed(2)} xP`}
              className="flex w-[34px] flex-col items-center gap-px rounded-[5px] border border-black/[.06] py-0.5 dark:border-white/[.06]"
              style={{ background: `color-mix(in oklab, ${c} 12%, transparent)` }}
            >
              <span className="flex items-center gap-0.5 leading-none">
                <span className="font-mono text-[8px] text-black/45 dark:text-white/45">{getClub(f.opp).shortCode}</span>
                <span className="min-w-[7px] rounded-sm text-center text-[7px] font-bold tabular-nums text-white" style={{ background: c }}>
                  {f.fdr}
                </span>
              </span>
              <span className="text-[10px] font-bold leading-tight tabular-nums">{f.xp.toFixed(1)}</span>
            </span>
          );
        })}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1">
      {cells.map((f) => {
        const c = fdrColour(f.fdr);
        return (
          <span
            key={f.gw}
            title={`GW${f.gw} vs ${f.opp} (${f.home ? "H" : "A"}) — FDR ${f.fdr}`}
            className="flex flex-1 items-center justify-center gap-1 rounded-[7px] border border-black/[.06] px-1 py-[3px] dark:border-white/[.06]"
            style={{ background: `color-mix(in oklab, ${c} 12%, transparent)` }}
          >
            <span className="min-w-[11px] rounded-[3px] text-center text-[9px] font-bold tabular-nums text-white" style={{ background: c }}>
              {f.fdr}
            </span>
            <span className="font-mono text-[10px] font-semibold">{getClub(f.opp).shortCode}</span>
            <span className="text-[9px] text-black/40 dark:text-white/40">({f.home ? "H" : "A"})</span>
            <span className="text-[11px] font-semibold tabular-nums">{f.xp.toFixed(1)}</span>
          </span>
        );
      })}
    </div>
  );
}
