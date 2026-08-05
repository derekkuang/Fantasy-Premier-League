"use client";
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
    <h2 className="t-label mb-2 px-1 text-xs text-black/50 dark:text-white/50">
      {children}
    </h2>
  );
}

/** A big number with a caption underneath — the projected-points hero, bank, etc. */
export function Stat({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="flex flex-col">
      <span className="t-display text-3xl font-bold tabular-nums">{value}</span>
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

export type FlagDetail = { note: string; rows: { name: string; value: string }[] };

/** A squad-health verdict. With `detail` it becomes a disclosure: the headline says what
 *  is wrong, one tap says who it is about.
 *
 *  "3 starters are rotation risks" is a verdict you then have to go and investigate on the
 *  pitch. Naming the three turns it into something you can act on without leaving the card,
 *  and keeps the summary as short as it was. No animation: this pushes the cards below it
 *  down the page, and sliding content a reader is mid-sentence in helps nobody.
 *
 *  Open state is owned by the caller, not by each flag, so a group of them can behave as an
 *  accordion — see BalanceCard. Several open at once pushes the whole column around and
 *  turns a scannable list of verdicts into a wall. */
export function Flag({
  level,
  detail,
  open = false,
  onToggle,
  children,
}: {
  level: string;
  detail?: FlagDetail;
  open?: boolean;
  onToggle?: () => void;
  children: ReactNode;
}) {
  const style = FLAG_STYLES[level] ?? "border-black/10 dark:border-white/10";
  const icon = <span className="select-none pt-px">{FLAG_ICONS[level] ?? "-"}</span>;

  if (!detail) {
    return (
      <div className={"flex items-start gap-2 rounded-lg border px-3 py-2 text-sm " + style}>
        {icon}
        <span>{children}</span>
      </div>
    );
  }

  return (
    <div className={"rounded-lg border text-sm " + style}>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="press flex w-full items-start gap-2 px-3 py-2 text-left"
      >
        {icon}
        <span className="flex-1">{children}</span>
        <span
          aria-hidden
          className={`select-none pt-px text-[10px] opacity-60 ${open ? "rotate-180" : ""}`}
        >
          ▾
        </span>
      </button>

      {open && (
        <div className="flex flex-col gap-1.5 border-t border-current/15 px-3 pb-2.5 pt-2">
          {detail.rows.map((r, i) => (
            <div key={i} className="flex items-baseline justify-between gap-3 text-[12px]">
              <span className="min-w-0 font-semibold">{r.name}</span>
              <span className="flex-none text-right tabular-nums opacity-75">{r.value}</span>
            </div>
          ))}
          <p className="pt-0.5 text-[11px] leading-relaxed opacity-70">{detail.note}</p>
        </div>
      )}
    </div>
  );
}
