"use client";
// True-FDR fixture ticker: teams down, gameweeks across, each cell coloured by the model's
// difficulty (not FPL's static number). Toggle between attack difficulty (goals-for, for
// picking attackers) and defence difficulty (goals-against, for clean-sheet picks).

import { useState } from "react";
import type { FixturesResponse, TickerFixture } from "@/lib/api";
import { fdrColour, getClub } from "@/lib/clubs";

export function FixtureTicker({ data }: { data: FixturesResponse }) {
  const [view, setView] = useState<"attack" | "defence">("attack");

  // gameweek columns = the union of gws present, ascending
  const gws = [...new Set(data.teams.flatMap((t) => t.fixtures.map((f) => f.gw)))].sort((a, b) => a - b);
  const teams = [...data.teams].sort((a, b) => (a.team_name ?? "").localeCompare(b.team_name ?? ""));
  const fdr = (f: TickerFixture) => (view === "attack" ? f.attack_fdr : f.defence_fdr);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm text-black/55 dark:text-white/55">
          Difficulty from the match model&apos;s expected goals — 1 easiest, 5 hardest.
        </p>
        <div className="flex flex-none gap-1">
          {(["attack", "defence"] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${
                view === v
                  ? "border-emerald-600 bg-emerald-600 text-white"
                  : "border-black/10 text-black/55 dark:border-white/10 dark:text-white/55"
              }`}
            >
              {v === "attack" ? "attack" : "defence"}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto rounded-2xl border border-black/10 dark:border-white/10">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="bg-black/[.03] dark:bg-white/[.04]">
              <th className="sticky left-0 z-10 bg-[var(--background)] px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-black/40 dark:text-white/40">
                Team
              </th>
              {gws.map((g) => (
                <th key={g} className="px-2 py-2 text-[11px] font-semibold text-black/40 dark:text-white/40">
                  GW{g}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {teams.map((t) => {
              const club = getClub(t.team_name);
              const byGw = new Map(t.fixtures.map((f) => [f.gw, f]));
              return (
                <tr key={t.team_id} className="border-t border-black/[.06] dark:border-white/[.06]">
                  <td className="sticky left-0 z-10 bg-[var(--background)] px-3 py-1.5">
                    <span className="flex items-center gap-1.5">
                      <span className="h-2.5 w-2.5 flex-none rounded-sm" style={{ background: club.primary }} />
                      <span className="font-mono text-[12px] font-semibold">{club.shortCode}</span>
                    </span>
                  </td>
                  {gws.map((g) => {
                    const f = byGw.get(g);
                    if (!f) return <td key={g} className="px-2 py-1.5 text-center text-black/20">—</td>;
                    return (
                      <td key={g} className="px-1.5 py-1.5">
                        <div
                          className="flex flex-col items-center rounded-md px-1 py-1 text-white"
                          style={{ background: fdrColour(fdr(f)) }}
                          title={`vs ${f.opp} (${f.home ? "H" : "A"}) — λ ${f.lam_for.toFixed(1)}/${f.lam_against.toFixed(1)}`}
                        >
                          <span className="font-mono text-[11px] font-semibold leading-tight">
                            {getClub(f.opp).shortCode}
                          </span>
                          <span className="text-[9px] leading-tight opacity-80">{f.home ? "H" : "A"}</span>
                        </div>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
