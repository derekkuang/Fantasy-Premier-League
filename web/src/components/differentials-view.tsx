"use client";
// Differential finder: high-xP, low-owned players ranked by differential value
// (xP × (1 − ownership)), with a max-ownership slider + position filter + xP floor.
// Mirrors fpledge.differentials.find_differentials over the precomputed predictions.

import { useMemo, useState } from "react";
import type { Prediction } from "@/lib/api";
import { getClub } from "@/lib/clubs";

const POSITIONS = ["ALL", "GK", "DEF", "MID", "FWD"] as const;
const MIN_XP = 3.5;

export function DifferentialsView({ predictions }: { predictions: Prediction[] }) {
  const [maxOwn, setMaxOwn] = useState(15);
  const [pos, setPos] = useState<(typeof POSITIONS)[number]>("ALL");

  const rows = useMemo(
    () =>
      predictions
        .filter(
          (p) =>
            !p.low_coverage &&
            p.ownership <= maxOwn &&
            p.xp >= MIN_XP &&
            (pos === "ALL" || p.position === pos),
        )
        .sort((a, b) => b.diff_value - a.diff_value)
        .slice(0, 25),
    [predictions, maxOwn, pos],
  );

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
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
        <label className="flex items-center gap-2 text-sm text-black/55 dark:text-white/55">
          max ownership
          <input type="range" min={1} max={40} value={maxOwn} onChange={(e) => setMaxOwn(Number(e.target.value))} className="accent-emerald-600" />
          <span className="w-8 tabular-nums font-semibold text-black/70 dark:text-white/70">{maxOwn}%</span>
        </label>
      </div>

      <div className="flex flex-col gap-2">
        {rows.map((p) => {
          const club = getClub(p.team);
          return (
            <div
              key={p.element_id}
              className="flex items-center gap-3 rounded-xl border border-black/10 bg-white/70 px-3 py-2.5 dark:border-white/10 dark:bg-white/5"
            >
              <span className="h-3 w-3 flex-none rounded-sm" style={{ background: club.primary }} />
              <div className="flex min-w-0 flex-1 flex-col">
                <span className="truncate font-semibold">{p.web_name}</span>
                <span className="text-[11px] text-black/45 dark:text-white/45">
                  {p.position} · {p.team} · £{p.price.toFixed(1)} · {p.ownership.toFixed(1)}% owned
                </span>
              </div>
              <div className="flex flex-none flex-col items-end">
                <span className="font-semibold tabular-nums">{p.xp.toFixed(2)} xP</span>
                <span className="text-[11px] text-emerald-600 tabular-nums">diff {p.diff_value.toFixed(2)}</span>
              </div>
            </div>
          );
        })}
        {rows.length === 0 && (
          <p className="text-sm text-black/50 dark:text-white/50">
            No players under {maxOwn}% ownership clear the {MIN_XP} xP floor — raise the slider.
          </p>
        )}
      </div>
      <p className="text-xs text-black/40 dark:text-white/40">
        Ranked by differential value = xP × (1 − ownership), among reliable-data players with xP ≥ {MIN_XP}.
      </p>
    </div>
  );
}
