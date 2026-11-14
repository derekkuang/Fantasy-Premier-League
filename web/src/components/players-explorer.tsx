"use client";
// Players: every player, one list. It replaces two pages, Predictions and Differentials, which
// showed the same players with different filters, different sheets and different names for the
// same numbers.
//
// On screen: a row of views (All players, Low owned, Budget, Penalty takers, Next 8 weeks), the
// position filter and a search box. Everything else (sort, horizon, ownership bands, the
// minimum xP, the price cap) lives in one Filters sheet, because most visits never touch it.
// A phone row carries one number, the one the list is sorted by; the desktop table adds the
// next three fixtures, where there is room for them.

import { useMemo, useState } from "react";
import type { PredictionRow as Prediction } from "@/lib/api";
import { getClub } from "@/lib/clubs";
import { Jersey } from "@/components/jersey";
import { DEFAULT_PAGE_SIZE, Pagination, pageOf, type PageSize } from "@/components/pagination";
import { Next3Strip } from "@/components/next3-strip";
import { PlayerSheet } from "@/components/player-sheet";
import { Sheet, SheetClose } from "@/components/sheet";
import { Explained } from "@/components/explained";
import { oppLabel } from "@/components/season-history";

type Pos = "ALL" | "GK" | "DEF" | "MID" | "FWD";
type Horizon = "xp" | "xp_next3" | "xp_next8";
type Sort = "xp" | "edge" | "value" | "price" | "ownership";

type Filters = {
  q: string; pos: Pos; bands: number[]; xpFloor: number; priceMax: number;
  pensOnly: boolean; horizon: Horizon; sort: Sort; lowDataOut: boolean;
};

const BASE: Filters = {
  q: "", pos: "ALL", bands: [1, 2, 3, 4, 5], xpFloor: 0, priceMax: 16,
  pensOnly: false, horizon: "xp", sort: "xp", lowDataOut: false,
};

export type ViewId = "all" | "low-owned" | "budget" | "pens" | "run";

const VIEWS: { id: ViewId; label: string; hint: string; patch: Partial<Filters> }[] = [
  { id: "all", label: "All players", hint: "Everyone, by projected points this gameweek.", patch: {} },
  { id: "low-owned", label: "Low owned", hint: "Under 15% owned, ranked by what owning them gains you on the average manager.",
    patch: { bands: [3, 4, 5], xpFloor: 3.5, sort: "edge", lowDataOut: true } },
  { id: "budget", label: "Budget", hint: "£5.5m and under, ranked by projected points per £m.",
    patch: { priceMax: 5.5, sort: "value" } },
  { id: "pens", label: "Penalty takers", hint: "First-choice penalty takers, by projected points.",
    patch: { pensOnly: true } },
  { id: "run", label: "Next 8 weeks", hint: "Projected points over the next eight gameweeks.",
    patch: { horizon: "xp_next8" } },
];

const POSITIONS: Pos[] = ["ALL", "GK", "DEF", "MID", "FWD"];
const BANDS = [1, 2, 3, 4, 5];
const BAND_NAME: Record<number, string> = { 1: "30%+", 2: "15–30%", 3: "7–15%", 4: "2–7%", 5: "under 2%" };
const SORTS: [Sort, string][] = [
  ["xp", "Projected points"], ["edge", "Edge"], ["value", "Points per £m"], ["price", "Price"], ["ownership", "Ownership"],
];
const HORIZONS: [Horizon, string][] = [["xp", "This GW"], ["xp_next3", "Next 3"], ["xp_next8", "Next 8"]];

const chip = (on: boolean) =>
  `press flex-none rounded-full border px-3 py-1.5 text-[13px] font-semibold ${
    on ? "border-emerald-600 bg-emerald-600 text-white" : "border-[var(--line)] text-muted hover:text-[var(--fg)]"
  }`;

const eo = (p: Prediction) => Math.max(0, Math.min(p.ownership / 100, 1));
// xp_next8 is summed in toRow BEFORE the fixture list is trimmed to three; never re-sum it here.
const hzXp = (p: Prediction, h: Horizon) => (h === "xp_next3" ? p.xp_next3 : h === "xp_next8" ? p.xp_next8 : p.xp);
const HZ_LABEL: Record<Horizon, string> = { xp: "xP", xp_next3: "next 3", xp_next8: "next 8" };

function metric(p: Prediction, f: Filters): number {
  const x = hzXp(p, f.horizon);
  if (f.sort === "edge") return x * (1 - eo(p));
  if (f.sort === "value") return p.price ? x / p.price : 0;
  if (f.sort === "price") return p.price;
  if (f.sort === "ownership") return p.ownership;
  return x;
}

function shown(p: Prediction, f: Filters): { value: string; label: string } {
  const m = metric(p, f);
  if (f.sort === "edge") return { value: `+${m.toFixed(1)}`, label: "edge" };
  if (f.sort === "value") return { value: m.toFixed(2), label: "per £m" };
  if (f.sort === "price") return { value: `£${m.toFixed(1)}`, label: "price" };
  if (f.sort === "ownership") return { value: `${m.toFixed(1)}%`, label: "owned" };
  return { value: m.toFixed(1), label: HZ_LABEL[f.horizon] };
}

export function PlayersExplorer({ predictions, gw, initialView = "all" }: {
  predictions: Prediction[];
  gw: number;
  initialView?: ViewId;
}) {
  const start = VIEWS.find((v) => v.id === initialView) ?? VIEWS[0];
  const [f, setF] = useState<Filters>({ ...BASE, ...start.patch });
  const [view, setView] = useState<ViewId | null>(start.id);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [openId, setOpenId] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<PageSize>(DEFAULT_PAGE_SIZE);

  // Search and position narrow a view; anything else makes it a custom one.
  const patch = (o: Partial<Filters>) => {
    setF((prev) => ({ ...prev, ...o }));
    if (Object.keys(o).some((k) => k !== "q" && k !== "pos")) setView(null);
    setPage(1);
  };
  const pick = (id: ViewId) => {
    const v = VIEWS.find((x) => x.id === id)!;
    setF((prev) => ({ ...BASE, q: prev.q, pos: prev.pos, ...v.patch }));
    setView(id);
    setPage(1);
  };

  const passes = useMemo(() => {
    const needle = f.q.trim().toLowerCase();
    return (p: Prediction, ignoreBands = false) =>
      (!f.lowDataOut || !p.low_coverage) &&
      (f.pos === "ALL" || p.position === f.pos) &&
      (needle === "" || p.web_name.toLowerCase().includes(needle) || (p.team ?? "").toLowerCase().includes(needle)) &&
      hzXp(p, f.horizon) >= f.xpFloor &&
      p.price <= f.priceMax &&
      (!f.pensOnly || p.set_pieces.penalties === 1) &&
      (ignoreBands || f.bands.includes(p.risk_tier));
  }, [f]);

  const rows = useMemo(
    () => predictions.filter((p) => passes(p)).sort((a, b) =>
      f.sort === "price" || f.sort === "ownership" ? metric(b, f) - metric(a, f) || b.xp - a.xp : metric(b, f) - metric(a, f)),
    [predictions, passes, f],
  );
  const bandCounts = useMemo(() => {
    const out: Record<number, number> = {};
    for (const t of BANDS) out[t] = predictions.filter((p) => p.risk_tier === t && passes(p, true)).length;
    return out;
  }, [predictions, passes]);

  const custom = (Object.keys(BASE) as (keyof Filters)[])
    .filter((k) => k !== "q" && k !== "pos")
    .filter((k) => JSON.stringify(f[k]) !== JSON.stringify(BASE[k])).length;
  const pg = pageOf(rows, page, pageSize);
  const open = openId != null ? predictions.find((p) => p.element_id === openId) ?? null : null;
  const hint = view ? VIEWS.find((v) => v.id === view)!.hint : "Your own filters.";

  return (
    <div className="flex flex-col gap-3">
      {/* views */}
      <div className="-mx-4 flex gap-1.5 overflow-x-auto px-4 pb-0.5 [scrollbar-width:none]">
        {VIEWS.map((v) => (
          <button key={v.id} onClick={() => pick(v.id)} aria-pressed={view === v.id} className={chip(view === v.id)}>
            {v.label}
          </button>
        ))}
      </div>

      {/* position, filters, search */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-2">
          <div className="flex gap-1" role="group" aria-label="Position">
            {POSITIONS.map((p) => (
              <button
                key={p}
                onClick={() => patch({ pos: p })}
                aria-pressed={f.pos === p}
                className={`press min-h-9 rounded-full px-2.5 text-[12px] font-semibold ${
                  f.pos === p ? "bg-[var(--fg)] text-[var(--background)]" : "text-muted hover:text-[var(--fg)]"
                }`}
              >
                {p === "ALL" ? "All" : p}
              </button>
            ))}
          </div>
          <button
            onClick={() => setFiltersOpen(true)}
            className="press flex min-h-9 flex-none items-center gap-1.5 rounded-full border border-[var(--line)] px-3 text-[13px] font-semibold"
          >
            Filters
            {custom > 0 && (
              <span className="grid h-5 min-w-5 place-items-center rounded-full bg-emerald-600 px-1 text-[11px] text-white">{custom}</span>
            )}
          </button>
        </div>
        <input
          value={f.q}
          onChange={(e) => patch({ q: e.target.value })}
          placeholder="Search player or club"
          aria-label="Search player or club"
          className="min-h-10 w-full min-w-0 rounded-full border border-[var(--line)] bg-transparent px-4 text-[14px] outline-none ring-[var(--focus)] focus:ring-2"
        />
      </div>

      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        {f.sort === "edge" ? (
          <Explained label="What is edge?" head={<span className="text-[13px] text-muted">{hint}</span>}>
            Edge is what owning a player gains you on the average manager: his projected points
            times the share of managers who don&apos;t own him. A low-owned player can have a
            bigger edge than a star who projects more.
          </Explained>
        ) : (
          <span className="text-[13px] text-muted">{hint}</span>
        )}
        <span className="text-[13px] tabular-nums text-muted">{rows.length} players</span>
      </div>

      {rows.length === 0 ? (
        <div className="flex flex-col items-start gap-2 rounded-2xl border border-[var(--line)] p-4">
          <p className="text-[14px]">No players match these filters.</p>
          <button onClick={() => pick("all")} className={chip(false)}>Show all players</button>
        </div>
      ) : (
        <>
          {/* phones and tablets: one number per row */}
          <ul className="overflow-hidden rounded-2xl border border-[var(--line)] lg:hidden">
            {pg.slice.map((p, i) => (
              <Row key={p.element_id} p={p} rank={pg.from + i + 1} f={f} onOpen={setOpenId} />
            ))}
          </ul>

          {/* desktop: a table with the fixtures, where there is room for them */}
          <div className="hidden lg:block">
            <Table rows={pg.slice} rankFrom={pg.from} f={f} gw={gw} onSort={(s) => patch({ sort: s })} onOpen={setOpenId} />
          </div>

          <Pagination
            current={pg.current} pageCount={pg.pageCount} from={pg.from} to={pg.to}
            total={rows.length} size={pageSize} setPage={setPage} setSize={setPageSize}
          />
        </>
      )}

      {filtersOpen && (
        <FiltersSheet
          f={f} patch={patch} bandCounts={bandCounts} matching={rows.length}
          reset={() => pick("all")} onClose={() => setFiltersOpen(false)}
        />
      )}
      {open && <PlayerSheet player={open} gw={gw} onClose={() => setOpenId(null)} />}
    </div>
  );
}

function Badges({ p }: { p: Prediction }) {
  const a = p.availability;
  const flagged = a.status != null && a.status !== "a";
  return (
    <>
      {p.set_pieces.penalties === 1 && (
        <span title="First-choice penalty taker" className="flex-none rounded bg-[var(--emerald-deep)] px-1.5 py-px text-[11px] font-bold text-white">
          PEN
        </span>
      )}
      {flagged && (
        <span
          title={`${a.label ?? ""}${a.news ? `: ${a.news}` : ""}`}
          className="flex-none rounded bg-[var(--amber-bg)] px-1.5 py-px text-[11px] font-bold text-[var(--amber-fg)]"
        >
          {a.factor > 0 && a.chance != null ? `${a.chance}%` : (a.label ?? "out")}
        </span>
      )}
    </>
  );
}

function Row({ p, rank, f, onOpen }: { p: Prediction; rank: number; f: Filters; onOpen: (id: number) => void }) {
  const club = getClub(p.team);
  const next = p.fixtures?.[0];
  const s = shown(p, f);
  return (
    <li>
      <button
        type="button"
        onClick={() => onOpen(p.element_id)}
        className="press flex min-h-14 w-full items-center gap-2.5 border-b border-[var(--line)] px-3 py-2 text-left hover:bg-black/[.02] dark:hover:bg-white/[.03]"
      >
        <span className="w-5 flex-none text-right font-mono text-[11px] tabular-nums text-muted">{rank}</span>
        <Jersey primary={club.primary} secondary={club.secondary} pattern={club.pattern} width={24} height={23} className="block flex-none" />
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="flex min-w-0 items-center gap-1.5">
            <span className="truncate text-[14px] font-semibold">{p.web_name}</span>
            <span className="flex-none font-mono text-[11px] text-muted">{club.shortCode}</span>
            <Badges p={p} />
          </span>
          <span className="truncate text-[12px] tabular-nums text-muted">
            {p.position} · £{p.price.toFixed(1)}m · {p.ownership.toFixed(1)}%
            {next ? ` · v ${oppLabel(next.opp, next.home)}` : " · blank"}
          </span>
        </span>
        <span className="flex w-14 flex-none flex-col items-end">
          <span className="t-title text-[18px] font-bold leading-none tabular-nums" style={{ color: "var(--emerald-text)" }}>
            {s.value}
          </span>
          <span className="text-[11px] text-muted">{s.label}</span>
        </span>
      </button>
    </li>
  );
}

const th = "px-2 py-2 text-[12px] font-semibold text-muted";

function SortTh({ label, s, f, onSort, align = "right" }: {
  label: string; s: Sort; f: Filters; onSort: (s: Sort) => void; align?: "left" | "right";
}) {
  const on = f.sort === s;
  return (
    <th className={`${th} ${align === "left" ? "text-left" : "text-right"}`} aria-sort={on ? "descending" : "none"}>
      <button onClick={() => onSort(s)} className={on ? "text-[var(--emerald-text)]" : "hover:text-[var(--fg)]"}>
        {label}{on ? " ↓" : ""}
      </button>
    </th>
  );
}

function Table({ rows, rankFrom, f, gw, onSort, onOpen }: {
  rows: Prediction[]; rankFrom: number; f: Filters; gw: number;
  onSort: (s: Sort) => void; onOpen: (id: number) => void;
}) {
  const extra = f.sort === "edge" || f.sort === "value";
  const xpHead = f.horizon === "xp" ? `xP GW${gw}` : HZ_LABEL[f.horizon];
  return (
    <div className="overflow-x-auto rounded-2xl border border-[var(--line)]">
      <table className="w-full border-collapse text-[14px]">
        <thead>
          <tr className="border-b border-[var(--line)]">
            <th className={`${th} w-10 text-left`}>#</th>
            <th className={`${th} text-left`}>Player</th>
            <SortTh label="£" s="price" f={f} onSort={onSort} />
            <SortTh label="Owned" s="ownership" f={f} onSort={onSort} />
            <th className={`${th} w-[260px] text-left`}>Next 3</th>
            {extra && <th className={`${th} text-right`}>{f.sort === "edge" ? "Edge" : "Per £m"}</th>}
            <SortTh label={xpHead} s="xp" f={f} onSort={onSort} />
          </tr>
        </thead>
        <tbody>
          {rows.map((p, i) => {
            const club = getClub(p.team);
            return (
              <tr
                key={p.element_id}
                onClick={() => onOpen(p.element_id)}
                className="cursor-pointer border-b border-[var(--line)] last:border-0 hover:bg-black/[.02] dark:hover:bg-white/[.03]"
              >
                <td className="px-2 py-2 font-mono text-[12px] tabular-nums text-muted">{rankFrom + i + 1}</td>
                <td className="px-2 py-2">
                  <button type="button" onClick={(e) => { e.stopPropagation(); onOpen(p.element_id); }} className="flex items-center gap-2 text-left">
                    <Jersey primary={club.primary} secondary={club.secondary} pattern={club.pattern} width={24} height={23} className="block flex-none" />
                    <span className="font-semibold">{p.web_name}</span>
                    <span className="font-mono text-[12px] text-muted">{club.shortCode} · {p.position}</span>
                    <Badges p={p} />
                  </button>
                </td>
                <td className="px-2 py-2 text-right tabular-nums">£{p.price.toFixed(1)}</td>
                <td className="px-2 py-2 text-right tabular-nums">{p.ownership.toFixed(1)}%</td>
                <td className="px-2 py-2"><Next3Strip fixtures={p.fixtures} /></td>
                {extra && <td className="px-2 py-2 text-right font-semibold tabular-nums">{shown(p, f).value}</td>}
                <td className="px-2 py-2 text-right text-[16px] font-bold tabular-nums" style={{ color: "var(--emerald-text)" }}>
                  {hzXp(p, f.horizon).toFixed(1)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function FiltersSheet({ f, patch, bandCounts, matching, reset, onClose }: {
  f: Filters; patch: (o: Partial<Filters>) => void; bandCounts: Record<number, number>;
  matching: number; reset: () => void; onClose: () => void;
}) {
  const label = "text-[13px] font-semibold";
  return (
    <Sheet onClose={onClose} label="Filters" className="lg:max-w-[480px] lg:rounded-[20px]">
      {(dismiss) => (
        <>
          <div className="flex items-center justify-between gap-3">
            <span className="t-title text-[18px] font-semibold">Filters</span>
            <SheetClose onClick={dismiss} />
          </div>

          <div className="flex flex-col gap-2">
            <span className={label}>Sort by</span>
            <div className="flex flex-wrap gap-1.5">
              {SORTS.map(([s, l]) => (
                <button key={s} onClick={() => patch({ sort: s })} aria-pressed={f.sort === s} className={chip(f.sort === s)}>{l}</button>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <span className={label}>Projected points over</span>
            <div className="flex flex-wrap gap-1.5">
              {HORIZONS.map(([h, l]) => (
                <button key={h} onClick={() => patch({ horizon: h })} aria-pressed={f.horizon === h} className={chip(f.horizon === h)}>{l}</button>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <span className={label}>Ownership</span>
            <div className="flex flex-wrap gap-1.5">
              {BANDS.map((t) => {
                const on = f.bands.includes(t);
                return (
                  <button
                    key={t}
                    aria-pressed={on}
                    onClick={() => patch({ bands: on ? f.bands.filter((x) => x !== t) : [...f.bands, t].sort() })}
                    className={chip(on)}
                  >
                    {BAND_NAME[t]} <span className="font-normal tabular-nums opacity-80">{bandCounts[t] ?? 0}</span>
                  </button>
                );
              })}
            </div>
          </div>

          <label className="flex flex-col gap-1.5">
            <span className={label}>Minimum projected points: {f.xpFloor.toFixed(1)}</span>
            <input type="range" min={0} max={20} step={0.5} value={f.xpFloor}
              onChange={(e) => patch({ xpFloor: Number(e.target.value) })} className="accent-emerald-600" />
          </label>

          <label className="flex flex-col gap-1.5">
            <span className={label}>Maximum price: £{f.priceMax.toFixed(1)}m</span>
            <input type="range" min={4} max={16} step={0.5} value={f.priceMax}
              onChange={(e) => patch({ priceMax: Number(e.target.value) })} className="accent-emerald-600" />
          </label>

          <label className="flex min-h-11 items-center justify-between gap-3">
            <span className={label}>First-choice penalty takers only</span>
            <input type="checkbox" checked={f.pensOnly} onChange={(e) => patch({ pensOnly: e.target.checked })}
              className="h-5 w-5 accent-emerald-600" />
          </label>

          <div className="flex gap-2 pt-1">
            <button onClick={reset} className={chip(false)}>Reset</button>
            <button onClick={dismiss} className="press flex-1 rounded-full bg-emerald-600 px-4 py-2 text-[14px] font-semibold text-white">
              Show {matching} players
            </button>
          </div>
        </>
      )}
    </Sheet>
  );
}
