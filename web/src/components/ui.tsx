// Tiny hand-rolled UI primitives (Tailwind classes only, no dependency).
// A component is just a function returning markup; `children` is whatever you nest
// inside it. We can swap these for shadcn/ui components later without touching pages.

import type { ReactNode } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={
        "rounded-2xl border border-black/10 bg-white/70 shadow-sm backdrop-blur " +
        "dark:border-white/10 dark:bg-white/5 " +
        className
      }
    >
      {children}
    </div>
  );
}

export function SectionTitle({ children }: { children: ReactNode }) {
  return (
    <h2 className="mb-2 px-1 text-xs font-semibold uppercase tracking-wider text-black/50 dark:text-white/50">
      {children}
    </h2>
  );
}

/** A big number with a caption underneath — the projected-points hero, bank, etc. */
export function Stat({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="flex flex-col">
      <span className="text-3xl font-bold tabular-nums leading-none">{value}</span>
      <span className="mt-1 text-xs text-black/50 dark:text-white/50">{label}</span>
      {sub ? <span className="text-xs text-black/40 dark:text-white/40">{sub}</span> : null}
    </div>
  );
}

const POS_COLORS: Record<string, string> = {
  GK: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
  DEF: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  MID: "bg-sky-500/15 text-sky-700 dark:text-sky-300",
  FWD: "bg-rose-500/15 text-rose-700 dark:text-rose-300",
};

export function PositionBadge({ position }: { position: string }) {
  return (
    <span
      className={
        "inline-flex w-9 justify-center rounded-md px-1.5 py-0.5 text-[11px] font-semibold " +
        (POS_COLORS[position] ?? "bg-black/10 dark:bg-white/10")
      }
    >
      {position}
    </span>
  );
}

const FLAG_STYLES: Record<string, string> = {
  warn: "bg-amber-500/10 text-amber-800 dark:text-amber-200 border-amber-500/30",
  info: "bg-sky-500/10 text-sky-800 dark:text-sky-200 border-sky-500/30",
  ok: "bg-emerald-500/10 text-emerald-800 dark:text-emerald-200 border-emerald-500/30",
};
const FLAG_ICONS: Record<string, string> = { warn: "⚠", info: "•", ok: "✓" };

export function Flag({ level, children }: { level: string; children: ReactNode }) {
  return (
    <div
      className={
        "flex items-start gap-2 rounded-lg border px-3 py-2 text-sm " +
        (FLAG_STYLES[level] ?? "border-black/10 dark:border-white/10")
      }
    >
      <span className="select-none">{FLAG_ICONS[level] ?? "-"}</span>
      <span>{children}</span>
    </div>
  );
}
