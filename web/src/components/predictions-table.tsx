"use client";
// Ranked xP table with a position filter, name/club search, and sort. Filters client-side
// over the precomputed predictions.

import { useMemo, useState } from "react";
import type { Prediction } from "@/lib/api";
import { getClub } from "@/lib/clubs";

const POSITIONS = ["ALL", "GK", "DEF", "MID", "FWD"] as const;
type Sort = "xp" | "price" | "ownership";

export function PredictionsTable({ predictions }: { predictions: Prediction[] }) {
  const [pos, setPos] = useState<(typeof POSITIONS)[number]>("ALL");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<Sort>("xp");

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const filtered = predictions.filter(
      (p) =>
        (pos === "ALL" || p.position === pos) &&
        (needle === "" || p.web_name.toLowerCase().includes(needle) || (p.team ?? "").toLowerCase().includes(needle)),
    );
    return filtered.sort((a, b) =>
      sort === "xp" ? b.xp - a.xp : sort === "price" ? b.price - a.price : b.ownership - a.ownership,
    );
  }, [predictions, pos, q, sort]);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex gap-1">
          {POSITIONS.map((p) => (
            <button
              key={p}
              onClick={() => setPos(p)}
              className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${
                pos === p ? "border-emerald-600 bg-emerald-600 text-white" : "border-black/10 text-black/55 dark:border-white/10 dark:text-white/55"
              }`}
            >
              {p}
            </button>
          ))}
        </div>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search player or club…"
          className="min-w-[160px] flex-1 rounded-full border border-black/15 bg-white px-3 py-1.5 text-sm outline-none dark:border-white/15 dark:bg-white/5"
        />
      </div>

      <div className="overflow-x-auto rounded-2xl border border-black/10 dark:border-white/10">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="bg-black/[.03] text-[11px] uppercase tracking-wide text-black/40 dark:bg-white/[.04] dark:text-white/40">
              <th className="px-3 py-2 text-left font-semibold">Player</th>
              <th className="px-2 py-2 text-left font-semibold">Pos</th>
              <SortTh label="£" active={sort === "price"} onClick={() => setSort("price")} />
              <SortTh label="Own%" active={sort === "ownership"} onClick={() => setSort("ownership")} />
              <SortTh label="xP" active={sort === "xp"} onClick={() => setSort("xp")} />
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => {
              const club = getClub(p.team);
              return (
                <tr key={p.element_id} className="border-t border-black/[.06] dark:border-white/[.06]">
                  <td className="px-3 py-1.5">
                    <span className="flex items-center gap-1.5">
                      <span className="h-2.5 w-2.5 flex-none rounded-sm" style={{ background: club.primary }} />
                      <span className="font-medium">{p.web_name}</span>
                      <span className="font-mono text-[11px] text-black/35 dark:text-white/35">{club.shortCode}</span>
                    </span>
                  </td>
                  <td className="px-2 py-1.5 text-black/50 dark:text-white/50">{p.position}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums text-black/55 dark:text-white/55">£{p.price.toFixed(1)}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums text-black/45 dark:text-white/45">{p.ownership.toFixed(1)}</td>
                  <td className="px-3 py-1.5 text-right font-semibold tabular-nums">{p.xp.toFixed(2)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-black/40 dark:text-white/40">{rows.length} players</p>
    </div>
  );
}

function SortTh({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <th className="px-2 py-2 text-right font-semibold">
      <button onClick={onClick} className={active ? "text-emerald-600" : "hover:text-emerald-600"}>
        {label}
        {active ? " ↓" : ""}
      </button>
    </th>
  );
}
