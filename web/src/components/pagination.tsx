"use client";
// Shared pager for the ranked lists (Predictions, Differentials).
//
// These lists are long — Predictions is ~555 rows, and each row carries an inline jersey SVG
// and a fixture strip, so rendering the whole set is both heavy and unreadable. Paging keeps
// the DOM small and gives the list a sense of scale ("of 555") that an endless scroll hides.
//
// The page window never runs past the end: `pageOf` clamps, so a filter that shrinks the set
// lands you on the last page rather than on a blank one.

const SIZES = [25, 50, 100] as const;
export type PageSize = (typeof SIZES)[number];
export const DEFAULT_PAGE_SIZE: PageSize = 50;

const BTN =
  "press min-h-[30px] min-w-[30px] cursor-pointer rounded-full border px-2.5 py-[5px] text-xs font-semibold disabled:cursor-default disabled:opacity-40";
const ON = "border-emerald-600 bg-emerald-600 text-white";
const OFF = "border-black/10 text-black/55 dark:border-white/10 dark:text-white/60";

/** Clamp a page to the available range and return the slice bounds for it. */
export function pageOf<T>(rows: T[], page: number, size: number) {
  const pageCount = Math.max(1, Math.ceil(rows.length / size));
  const current = Math.min(Math.max(page, 1), pageCount);
  const from = (current - 1) * size;
  return { current, pageCount, slice: rows.slice(from, from + size), from, to: Math.min(from + size, rows.length) };
}

/** 1 … 4 5 6 … 12 — always first and last, a window of ±1 around the current page. */
function pageNumbers(current: number, pageCount: number): (number | "gap")[] {
  if (pageCount <= 7) return Array.from({ length: pageCount }, (_, i) => i + 1);
  const out: (number | "gap")[] = [1];
  const lo = Math.max(2, current - 1);
  const hi = Math.min(pageCount - 1, current + 1);
  if (lo > 2) out.push("gap");
  for (let i = lo; i <= hi; i++) out.push(i);
  if (hi < pageCount - 1) out.push("gap");
  out.push(pageCount);
  return out;
}

export function Pagination({
  current, pageCount, from, to, total, size, setPage, setSize, unit = "players",
}: {
  current: number; pageCount: number; from: number; to: number; total: number;
  size: PageSize; setPage: (p: number) => void; setSize: (s: PageSize) => void;
  unit?: string;
}) {
  if (total === 0) return null;

  return (
    <div className="flex flex-col gap-2.5 border-t border-black/[.06] pt-3 dark:border-white/[.06]">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-[11px] tabular-nums text-black/55 dark:text-white/60">
          Showing {from + 1}–{to} of {total} {unit}
        </span>
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] font-semibold uppercase tracking-[.07em] text-black/55 dark:text-white/60">
            per page
          </span>
          {SIZES.map((s) => (
            <button
              key={s}
              onClick={() => { setSize(s); setPage(1); }}
              className={`${BTN} ${size === s ? ON : OFF}`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {pageCount > 1 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <button onClick={() => setPage(current - 1)} disabled={current === 1} className={`${BTN} ${OFF}`}>
            ‹ Prev
          </button>
          {pageNumbers(current, pageCount).map((n, i) =>
            n === "gap" ? (
              <span key={`gap${i}`} className="px-1 text-xs text-black/55 dark:text-white/60">…</span>
            ) : (
              <button
                key={n}
                onClick={() => setPage(n)}
                aria-current={n === current ? "page" : undefined}
                className={`${BTN} tabular-nums ${n === current ? ON : OFF}`}
              >
                {n}
              </button>
            ),
          )}
          <button onClick={() => setPage(current + 1)} disabled={current === pageCount} className={`${BTN} ${OFF}`}>
            Next ›
          </button>
        </div>
      )}
    </div>
  );
}
