"use client";
// Predicted vs scored, this season, inside the player sheet's "Season so far" section. A bar is
// what he scored; the emerald tick is what this site published before that deadline, never
// recalculated with a later model. Weeks we did not project him carry no tick and count in
// neither total. Weeks we projected him for a club he had left say so (an out-of-date player
// list), rather than passing that projection off as one for the match he played. Tap or hover
// a week for its numbers; "Every gameweek" is the same data as a table.

import { useState } from "react";
import type { HistoryWeek } from "@/lib/api";
import { getClub } from "@/lib/clubs";

const CHART_H = 88; // px

/** The section header's summary, so the totals read without opening it. */
export function seasonTotals(weeks: HistoryWeek[]): { predicted: number; scored: number; n: number } {
  const projected = weeks.filter((w) => w.xp != null);
  return {
    predicted: projected.reduce((s, w) => s + (w.xp ?? 0), 0),
    scored: projected.reduce((s, w) => s + w.pts, 0),
    n: projected.length,
  };
}

/** Home fixtures in capitals, away in lower case: the FPL convention, and no "(H)" to read. */
export function oppLabel(opp: string, home: boolean): string {
  const code = getClub(opp).shortCode;
  return home ? code.toUpperCase() : code.toLowerCase();
}

function vsLabel(w: HistoryWeek): string | null {
  if (!w.vs.length) return null;
  return w.vs.map((v) => oppLabel(v.opp, v.home)).join(" + ");
}

function weekNote(w: HistoryWeek): string {
  const vs = vsLabel(w);
  return [
    `GW${w.gw}`,
    ...(vs ? [`v ${vs}`] : []),
    w.xp == null
      ? "not projected"
      : `predicted ${w.xp.toFixed(1)}${w.as_club ? ` as a ${w.as_club} player` : ""}`,
    `scored ${w.pts}`,
    w.mins > 0 ? `${w.mins}′` : "didn't play",
  ].join(" · ");
}

export function SeasonHistory({ weeks }: { weeks: HistoryWeek[] }) {
  const [active, setActive] = useState(weeks.length - 1);
  const shown = weeks[Math.min(active, weeks.length - 1)];

  const { predicted, scored, n } = seasonTotals(weeks);
  const diff = scored - predicted;
  const wrongClub = weeks.filter((w) => w.xp != null && w.as_club);
  const formerClubs = [...new Set(wrongClub.map((w) => w.as_club))].join(" / ");

  // One scale for both marks, from the lowest score (points can go negative) to the highest
  // of either; at least 4 so a quiet season doesn't fill the chart with noise.
  const top = Math.max(4, ...weeks.map((w) => Math.max(w.pts, w.xp ?? 0)));
  const floor = Math.min(0, ...weeks.map((w) => w.pts));
  const y = (v: number) => ((v - floor) / (top - floor)) * 100; // % up from the bottom
  const zero = y(0);
  const labelled = (w: HistoryWeek, i: number) =>
    weeks.length <= 12 || i === 0 || i === weeks.length - 1 || w.gw % 5 === 0;

  return (
    <div className="flex flex-col gap-2.5">
      <p className="text-[13px] leading-relaxed">
        {n > 0 ? (
          <>
            Over {n} gameweek{n === 1 ? "" : "s"} he scored{" "}
            <strong className="tabular-nums">{diff >= 0 ? `${diff.toFixed(1)} more` : `${Math.abs(diff).toFixed(1)} fewer`}</strong>{" "}
            points than we predicted.
          </>
        ) : (
          "We didn't project him in any finished gameweek, so there is nothing to total yet."
        )}
      </p>

      {wrongClub.length > 0 && (
        <p className="text-[12px] leading-relaxed text-[var(--amber-fg)]">
          {`In ${wrongClub.length} of these weeks we projected him as a ${formerClubs} player, ` +
            "from an out-of-date player list, so those projections were for the wrong club's matches."}
        </p>
      )}

      {/* the chart: one column per finalised gameweek */}
      <div className="flex flex-col gap-1">
        <span className="text-[11px] leading-none tabular-nums text-muted">{`top of chart ${top} pts`}</span>
        <div className="relative" style={{ height: CHART_H }}>
          <div
            className="absolute inset-x-0 border-t border-black/15 dark:border-white/20"
            style={{ bottom: `${zero}%` }}
          />
          <div className="absolute inset-0 flex gap-[2px]">
            {weeks.map((w, i) => {
              const h = Math.abs(y(w.pts) - zero);
              return (
                <button
                  key={w.gw}
                  type="button"
                  aria-label={weekNote(w)}
                  aria-pressed={i === active}
                  onClick={() => setActive(i)}
                  onPointerEnter={() => setActive(i)}
                  onFocus={() => setActive(i)}
                  className={`relative min-w-0 flex-1 rounded-[4px] outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)] ${
                    i === active ? "bg-black/[.05] dark:bg-white/[.08]" : ""
                  }`}
                >
                  {h > 0 && (
                    <span
                      className="absolute left-1/2 w-[60%] max-w-[14px] -translate-x-1/2 bg-black/30 dark:bg-white/35"
                      style={{
                        bottom: `${w.pts >= 0 ? zero : y(w.pts)}%`,
                        height: `${h}%`,
                        borderRadius: w.pts >= 0 ? "4px 4px 0 0" : "0 0 4px 4px",
                      }}
                    />
                  )}
                  {w.xp != null && (
                    <span
                      className="absolute left-1/2 h-[2px] w-[85%] max-w-[20px] -translate-x-1/2 rounded-full"
                      style={{
                        bottom: `calc(${y(w.xp)}% - 1px)`,
                        background: "var(--emerald-text)",
                        boxShadow: "0 0 0 1.5px var(--background)",
                      }}
                    />
                  )}
                </button>
              );
            })}
          </div>
        </div>
        <div className="flex gap-[2px]" aria-hidden>
          {weeks.map((w, i) => (
            <span key={w.gw} className="min-w-0 flex-1 text-center text-[11px] tabular-nums text-muted">
              {labelled(w, i) ? w.gw : ""}
            </span>
          ))}
        </div>
      </div>

      {/* readout for the tapped week, then the legend */}
      <p className="text-[12px] font-semibold tabular-nums" aria-live="polite">
        {weekNote(shown)}
      </p>
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-[12px] text-muted">
        <span className="flex items-center gap-1">
          <span className="inline-block h-2.5 w-2 rounded-t-[2px] bg-black/30 dark:bg-white/35" />
          scored
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-[2px] w-3 rounded-full" style={{ background: "var(--emerald-text)" }} />
          predicted before the deadline
        </span>
      </div>

      <details>
        <summary className="cursor-pointer text-[12px] font-semibold text-muted">Every gameweek</summary>
        <table className="mt-1 w-full text-[12px] tabular-nums">
          <thead>
            <tr className="text-[11px] text-muted">
              <th className="py-1 text-left font-normal">GW</th>
              <th className="py-1 text-left font-normal">v</th>
              <th className="py-1 text-right font-normal">predicted</th>
              <th className="py-1 text-right font-normal">scored</th>
              <th className="py-1 text-right font-normal">mins</th>
            </tr>
          </thead>
          <tbody>
            {[...weeks].reverse().map((w) => (
              <tr key={w.gw} className="border-t border-black/[.06] dark:border-white/[.06]">
                <td className="py-[5px]">{w.gw}</td>
                <td className="py-[5px] font-mono">{vsLabel(w) ?? "–"}</td>
                <td className="py-[5px] text-right">
                  {w.xp == null ? (
                    <span className="text-muted">not projected</span>
                  ) : (
                    <>
                      {w.xp.toFixed(1)}
                      {w.as_club && <span title={`projected as a ${w.as_club} player`}>†</span>}
                    </>
                  )}
                </td>
                <td className="py-[5px] text-right font-semibold">{w.pts}</td>
                <td className="py-[5px] text-right">{w.mins}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {wrongClub.length > 0 && (
          <p className="mt-1 text-[12px] text-muted">{`† projected as a ${formerClubs} player`}</p>
        )}
      </details>

      <p className="text-[12px] leading-relaxed text-muted">
        These are the projections this site published before each deadline, never recalculated,
        so earlier weeks show earlier versions of the model. One week says little; the total is
        the fairer read.
      </p>
    </div>
  );
}
