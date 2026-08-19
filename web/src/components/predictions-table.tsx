"use client";
// PredictionsExplorer: the ranked xP explorer. Owns metric / position / query / open-sheet
// state; renders a 44px-per-player list on mobile and a dense sortable table on desktop
// (lg+). The active rank metric is emphasised (emerald) in every row and kept in sync
// between the pills and the sortable table headers.

import { useMemo, useState } from "react";
import type { Prediction } from "@/lib/api";
import { getClub } from "@/lib/clubs";
import { Jersey } from "@/components/jersey";
import { DEFAULT_PAGE_SIZE, Pagination, pageOf, type PageSize } from "@/components/pagination";
import { Next3Strip } from "@/components/next3-strip";
import { PredictionSheet } from "@/components/prediction-sheet";

type Metric = "xp" | "xp_next3" | "price" | "ownership";
type Pos = "ALL" | "GK" | "DEF" | "MID" | "FWD";

const METRICS: [Metric, string][] = [
  ["xp", "This GW"],
  ["xp_next3", "Next 3 GWs"],
  ["price", "£ price"],
  ["ownership", "Own%"],
];
const POSITIONS: Pos[] = ["ALL", "GK", "DEF", "MID", "FWD"];

export function PredictionsExplorer({ predictions }: { predictions: Prediction[] }) {
  const [metric, setMetricState] = useState<Metric>("xp");
  const [pos, setPosState] = useState<Pos>("ALL");
  const [q, setQState] = useState("");
  const [openId, setOpenId] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<PageSize>(DEFAULT_PAGE_SIZE);

  // Any change to what is being ranked or filtered returns to page 1 — re-sorting while on
  // page 6 leaves you looking at ranks 251-300 of a list you have never seen the top of.
  const setMetric = (m: Metric) => { setMetricState(m); setPage(1); };
  const setPos = (p: Pos) => { setPosState(p); setPage(1); };
  const setQ = (s: string) => { setQState(s); setPage(1); };

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return predictions
      .filter(
        (p) =>
          (pos === "ALL" || p.position === pos) &&
          (needle === "" ||
            p.web_name.toLowerCase().includes(needle) ||
            (p.team ?? "").toLowerCase().includes(needle)),
      )
      .sort((a, b) => b[metric] - a[metric]);
  }, [predictions, metric, pos, q]);

  const open = openId != null ? predictions.find((p) => p.element_id === openId) ?? null : null;
  const gw = predictions[0]?.fixtures?.[0]?.gw;
  const pg = pageOf(rows, page, pageSize);

  return (
    <div className="flex flex-col gap-2">
      <Controls metric={metric} setMetric={setMetric} pos={pos} setPos={setPos} q={q} setQ={setQ} />

      {rows.length === 0 ? (
        <p className="text-[13px] text-black/50 dark:text-white/50">No players match that filter.</p>
      ) : (
        <>
          {/* mobile: hairline-separated rows in one container */}
          <ul className="overflow-hidden rounded-2xl border border-black/10 shadow-sm lg:hidden dark:border-white/10">
            {pg.slice.map((p, i) => (
              <PlayerRow key={p.element_id} p={p} rank={pg.from + i + 1} metric={metric} onOpen={setOpenId} />
            ))}
          </ul>

          {/* desktop: dense sortable table */}
          <div className="hidden lg:block">
            <PredictionsTable
              rows={pg.slice} rankFrom={pg.from} metric={metric} setMetric={setMetric} gw={gw} onOpen={setOpenId}
            />
          </div>

          <Pagination
            current={pg.current} pageCount={pg.pageCount} from={pg.from} to={pg.to}
            total={rows.length} size={pageSize} setPage={setPage} setSize={setPageSize}
          />
        </>
      )}

      {open && <PredictionSheet player={open} onClose={() => setOpenId(null)} />}
    </div>
  );
}

function Controls({
  metric,
  setMetric,
  pos,
  setPos,
  q,
  setQ,
}: {
  metric: Metric;
  setMetric: (m: Metric) => void;
  pos: Pos;
  setPos: (p: Pos) => void;
  q: string;
  setQ: (s: string) => void;
}) {
  const pill = (active: boolean) =>
    `press flex-none rounded-full border font-semibold ${
      active ? "border-emerald-600 bg-emerald-600 text-white" : "border-black/10 text-black/55 dark:border-white/10 dark:text-white/55"
    }`;
  return (
    // Its own block above the list, not a layer over it. Sticky chrome means the table
    // necessarily runs underneath, and no amount of tint makes a bar that rows are sliding
    // beneath stop reading as overlap — the fix is to stop stacking, not to stack more
    // opaquely. So: a bordered card that scrolls away with everything else, with the list
    // beginning cleanly below it.
    <div className="flex flex-col gap-2 rounded-2xl border border-black/10 p-2.5 shadow-sm dark:border-white/10">
      <div className="flex items-center gap-2 overflow-x-auto">
        <span className="t-label flex-none text-[10px] text-black/40 dark:text-white/40">
          Rank by
        </span>
        {METRICS.map(([m, label]) => (
          <button
            key={m}
            onClick={() => setMetric(m)}
            aria-pressed={metric === m}
            className={`${pill(metric === m)} min-h-8 px-3 py-1.5 text-xs`}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="flex items-center gap-2">
        <div className="flex gap-1">
          {POSITIONS.map((p) => (
            <button
              key={p}
              onClick={() => setPos(p)}
              aria-pressed={pos === p}
              className={`${pill(pos === p)} min-h-8 px-3 py-1.5 text-[11px]`}
            >
              {p}
            </button>
          ))}
        </div>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search player or club…"
          aria-label="Search player or club"
          // `outline-none` with nothing replacing it left keyboard users with no focus
          // indicator at all on the one control they have to type into.
          className="min-h-9 min-w-[160px] flex-1 rounded-full border border-black/15 bg-transparent px-3 py-1.5 text-sm outline-none ring-[var(--focus)] focus:ring-2 dark:border-white/15"
        />
      </div>
    </div>
  );
}

function PlayerRow({ p, rank, metric, onOpen }: { p: Prediction; rank: number; metric: Metric; onOpen: (id: number) => void }) {
  const club = getClub(p.team);
  return (
    <li
      role="button"
      tabIndex={0}
      onClick={() => onOpen(p.element_id)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen(p.element_id);
        }
      }}
      // A background tint was the only focus indicator here — too low-contrast to locate a
      // row by, and invisible to anyone who needs it most. The ring is the global default.
      className="press flex min-h-11 cursor-pointer items-center gap-2 border-b border-black/[.06] px-2.5 py-[7px] hover:bg-black/[.02] focus-visible:bg-black/[.03] dark:border-white/[.06] dark:hover:bg-white/[.03]"
    >
      <span className="w-4 flex-none text-right font-mono text-[10px] tabular-nums text-black/35 dark:text-white/35">{rank}</span>
      <Jersey primary={club.primary} secondary={club.secondary} pattern={club.pattern} width={22} height={21} className="block flex-none" />

      <div className="flex min-w-0 flex-1 flex-col gap-px">
        <div className="flex min-w-0 items-center gap-1">
          <span className="truncate text-[13px] font-semibold">{p.web_name}</span>
          <span className="flex-none font-mono text-[10px] text-black/35 dark:text-white/35">{club.shortCode}</span>
        </div>
        <span className="whitespace-nowrap text-[10px] tabular-nums text-black/40 dark:text-white/40">
          {p.position} ·{" "}
          <span className={metric === "price" ? "font-bold text-emerald-600" : ""}>£{p.price.toFixed(1)}</span> ·{" "}
          <span className={metric === "ownership" ? "font-bold text-emerald-600" : ""}>{p.ownership.toFixed(1)}%</span>
        </span>
      </div>

      <Next3Strip fixtures={p.fixtures} position={p.position} variant="chip" />

      <div className="flex w-9 flex-none flex-col items-end">
        <span className={`t-title text-[17px] font-bold leading-none tabular-nums ${metric === "xp" ? "text-emerald-600" : ""}`}>
          {p.xp.toFixed(1)}
        </span>
        <span className={`text-[10px] tabular-nums ${metric === "xp_next3" ? "text-emerald-600" : "text-black/40 dark:text-white/40"}`}>
          n3 {p.xp_next3.toFixed(1)}
        </span>
      </div>
    </li>
  );
}

const headCls = "px-2 py-2 t-label text-[11px] text-black/40 dark:text-white/40";

/** Module scope, not inside `PredictionsTable`'s render — see the note in captain-compare.tsx.
 *  A sortable header remounting on every render is the version of this bug a user can feel:
 *  clicking one moves focus, and a remount drops it, so keyboard sorting loses its place. */
function SortTh({
  label,
  m,
  metric,
  setMetric,
}: {
  label: string;
  m: Metric;
  metric: Metric;
  setMetric: (m: Metric) => void;
}) {
  const active = metric === m;
  return (
    <th className={`${headCls} text-right`} aria-sort={active ? "descending" : "none"}>
      <button
        onClick={() => setMetric(m)}
        className={
          active ? "text-emerald-600" : "text-black/40 hover:text-emerald-600 dark:text-white/40"
        }
      >
        {label}
        {active ? " ↓" : ""}
      </button>
    </th>
  );
}

function PredictionsTable({
  rows,
  rankFrom,
  metric,
  setMetric,
  gw,
  onOpen,
}: {
  rows: Prediction[];
  rankFrom: number;   // rank of the first row on this page, so numbering continues across pages
  metric: Metric;
  setMetric: (m: Metric) => void;
  gw: number | undefined;
  onOpen: (id: number) => void;
}) {
  const em = (on: boolean) => (on ? "text-emerald-600" : "");

  return (
    <div className="overflow-x-auto rounded-2xl border border-black/10 dark:border-white/10">
      <table className="w-full min-w-[820px] border-collapse text-sm">
        <thead>
          <tr className="bg-black/[.03] dark:bg-white/[.04]">
            <th className={`${headCls} w-[34px] text-left`}>#</th>
            <th className={`${headCls} text-left`}>Player</th>
            <th className={`${headCls} text-left`}>Pos</th>
            <SortTh label="£" m="price" metric={metric} setMetric={setMetric} />
            <SortTh label="Own%" m="ownership" metric={metric} setMetric={setMetric} />
            <SortTh label={`xP GW${gw ?? ""}`} m="xp" metric={metric} setMetric={setMetric} />
            <th className={`${headCls} w-[250px] text-left`}>Next 3 gameweeks</th>
            <SortTh label="N3 total" m="xp_next3" metric={metric} setMetric={setMetric} />
          </tr>
        </thead>
        <tbody>
          {rows.map((p, i) => {
            const club = getClub(p.team);
            return (
              <tr
                key={p.element_id}
                onClick={() => onOpen(p.element_id)}
                className="cursor-pointer border-t border-black/[.06] hover:bg-black/[.02] dark:border-white/[.06] dark:hover:bg-white/[.03]"
              >
                <td className="px-2 py-[7px] font-mono text-[11px] tabular-nums text-black/35 dark:text-white/35">{rankFrom + i + 1}</td>
                <td className="px-2 py-[7px]">
                  <span className="flex items-center gap-2">
                    <Jersey primary={club.primary} secondary={club.secondary} pattern={club.pattern} width={24} height={23} className="block flex-none" />
                    <span className="font-medium">{p.web_name}</span>
                    <span className="font-mono text-[11px] text-black/35 dark:text-white/35">{club.shortCode}</span>
                  </span>
                </td>
                <td className="px-2 py-[7px] text-[12px] text-black/50 dark:text-white/50">{p.position}</td>
                <td className={`px-2 py-[7px] text-right text-[13px] tabular-nums ${em(metric === "price")}`}>£{p.price.toFixed(1)}</td>
                <td className={`px-2 py-[7px] text-right text-[13px] tabular-nums ${em(metric === "ownership")}`}>{p.ownership.toFixed(1)}</td>
                <td className={`px-2 py-[7px] text-right text-[15px] font-bold tabular-nums ${em(metric === "xp")}`}>{p.xp.toFixed(1)}</td>
                <td className="w-[250px] px-2 py-[7px]">
                  <Next3Strip fixtures={p.fixtures} position={p.position} variant="row" />
                </td>
                <td className={`px-2 py-[7px] text-right text-[14px] font-bold tabular-nums ${em(metric === "xp_next3")}`}>{p.xp_next3.toFixed(1)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
