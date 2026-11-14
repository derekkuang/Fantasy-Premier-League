"use client";
// This season, week by week: our ranking score against FPL's own forecast, as a dumbbell per
// gameweek. The emerald dot is ours, the hollow one FPL's; the line between them is the gap,
// so who was ahead each week reads at a glance. Weeks without FPL's forecast show ours alone.
// Tap or hover a week for its numbers; the table under "Each gameweek" holds the same data.

import { useState } from "react";
import type { LiveRecord } from "@/lib/api";

const H = 150; // px
const TICKS = [0, 0.2, 0.4, 0.6];

export function LiveChart({ live }: { live: LiveRecord }) {
  const weeks = live.gws.filter((w) => w.ours.rho != null);
  const [active, setActive] = useState(weeks.length - 1);
  if (!weeks.length) return null;
  const shown = weeks[Math.min(active, weeks.length - 1)];

  const vals = weeks.flatMap((w) => [w.ours.rho ?? 0, w.fpl?.rho ?? 0]);
  const lo = Math.min(0, ...vals);
  const hi = Math.max(0.6, ...vals);
  const y = (v: number) => ((v - lo) / (hi - lo)) * 100;

  const note = (w: (typeof weeks)[number]) =>
    `GW${w.gw} · ours ${w.ours.rho!.toFixed(2)}` +
    (w.fpl?.rho != null ? ` · FPL ${w.fpl.rho.toFixed(2)}` : " · FPL's forecast not captured") +
    ` · ${w.n} players`;

  return (
    <div className="flex flex-col gap-2">
      <div className="relative" style={{ height: H }}>
        {/* gridlines with their values, recessive */}
        {TICKS.filter((t) => t >= lo && t <= hi).map((t) => (
          <div key={t} className="absolute inset-x-0 flex items-center gap-2" style={{ bottom: `${y(t)}%` }}>
            <span className="w-7 flex-none translate-y-1/2 text-right text-[11px] tabular-nums text-muted">{t.toFixed(1)}</span>
            <span className="h-px flex-1 bg-[var(--line)]" />
          </div>
        ))}
        <div className="absolute inset-y-0 left-9 right-0 flex gap-[2px]">
          {weeks.map((w, i) => {
            const ours = y(w.ours.rho!);
            const fpl = w.fpl?.rho != null ? y(w.fpl.rho) : null;
            return (
              <button
                key={w.gw}
                type="button"
                aria-label={note(w)}
                aria-pressed={i === active}
                onClick={() => setActive(i)}
                onPointerEnter={() => setActive(i)}
                onFocus={() => setActive(i)}
                className={`relative min-w-0 flex-1 rounded-[6px] outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)] ${
                  i === active ? "bg-black/[.04] dark:bg-white/[.07]" : ""
                }`}
              >
                {fpl != null && (
                  <span
                    className="absolute left-1/2 w-[2px] -translate-x-1/2 bg-black/20 dark:bg-white/25"
                    style={{ bottom: `${Math.min(ours, fpl)}%`, height: `${Math.abs(ours - fpl)}%` }}
                  />
                )}
                {fpl != null && (
                  <span
                    className="absolute left-1/2 h-[10px] w-[10px] -translate-x-1/2 translate-y-1/2 rounded-full border-2 border-[var(--muted)] bg-[var(--background)]"
                    style={{ bottom: `${fpl}%` }}
                  />
                )}
                <span
                  className="absolute left-1/2 h-[10px] w-[10px] -translate-x-1/2 translate-y-1/2 rounded-full"
                  style={{ bottom: `${ours}%`, background: "var(--emerald-text)", boxShadow: "0 0 0 2px var(--background)" }}
                />
              </button>
            );
          })}
        </div>
      </div>
      <div className="ml-9 flex gap-[2px]" aria-hidden>
        {weeks.map((w) => (
          <span key={w.gw} className="min-w-0 flex-1 text-center text-[11px] tabular-nums text-muted">{w.gw}</span>
        ))}
      </div>
      <p className="text-[13px] font-semibold tabular-nums" aria-live="polite">{note(shown)}</p>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-muted">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-[10px] w-[10px] rounded-full" style={{ background: "var(--emerald-text)" }} />
          our projections
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-[10px] w-[10px] rounded-full border-2 border-[var(--muted)]" />
          FPL&apos;s forecast before the deadline
        </span>
      </div>
    </div>
  );
}
