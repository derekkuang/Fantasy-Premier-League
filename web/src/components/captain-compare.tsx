"use client";
// Captain card with a compare table. Two bases: "rank-adjusted" (differential value
// 2·xP·(1−EO), gated by an xP floor) and "raw xP". Mirrors the backend rank module; the
// chosen captain (passed in) drives the pitch armband and the doubled points.

import type { SquadPlayer } from "@/lib/api";
import { xpFloor } from "@/lib/formation";

const capScore = (p: SquadPlayer) => p.captain_score ?? 2 * p.xp * (1 - (p.ownership ?? 0) / 100);

export function CaptainCompare({
  starters,
  basis,
  onBasis,
  captainId,
}: {
  starters: SquadPlayer[];
  basis: "rank" | "xp";
  onBasis: (b: "rank" | "xp") => void;
  captainId: number | null;
}) {
  const floor = xpFloor(starters);
  const pick = starters.find((p) => p.element_id === captainId) ?? null;
  const candidates = [...starters]
    .sort((a, b) => (basis === "xp" ? b.xp - a.xp : capScore(b) - capScore(a)))
    .slice(0, 5);

  const Toggle = ({ id, label, hint }: { id: "rank" | "xp"; label: string; hint: string }) => (
    <button
      type="button"
      onClick={() => onBasis(id)}
      title={hint}
      className={`rounded-full border px-2.5 py-1 text-[10px] font-semibold ${
        basis === id
          ? "border-emerald-600 bg-emerald-600 text-white"
          : "border-black/10 text-black/55 dark:border-white/10 dark:text-white/55"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between px-0.5">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-black/40 dark:text-white/40">
          Captain
        </h2>
        <div className="flex gap-1">
          <Toggle id="rank" label="rank-adjusted" hint="2·xP·(1−EO), gated by an xP floor" />
          <Toggle id="xp" label="raw xP" hint="highest raw xP" />
        </div>
      </div>

      <div className="flex flex-col gap-3 rounded-2xl border border-black/10 bg-white/70 p-4 shadow-sm dark:border-white/10 dark:bg-white/5">
        {pick && (
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <span className="grid h-5 w-5 flex-none place-items-center rounded-full bg-emerald-600 text-[11px] font-bold text-white">
                C
              </span>
              <div className="flex flex-col">
                <span className="text-[15px] font-semibold">{pick.web_name}</span>
                <span className="text-[11px] text-black/40 dark:text-white/40">
                  {pick.team} · {pick.ownership.toFixed(1)}% owned
                </span>
              </div>
            </div>
            <span className="tabular-nums text-[13px] text-black/55 dark:text-white/55">
              {pick.xp.toFixed(2)} xP × 2
            </span>
          </div>
        )}

        <div className="flex flex-col gap-0.5 border-t border-black/[.06] pt-2.5 dark:border-white/[.06]">
          <div className="grid grid-cols-[1fr_42px_46px_52px] gap-1.5 px-1.5 pb-1 text-[9px] font-semibold uppercase tracking-[0.06em] text-black/40 dark:text-white/40">
            <span>candidate</span>
            <span className="text-right">xP</span>
            <span className="text-right">owned</span>
            <span className="text-right">2xP(1−EO)</span>
          </div>
          {candidates.map((c) => {
            const isPick = c.element_id === captainId;
            const belowFloor = basis === "rank" && c.xp < floor;
            const verdict = isPick ? "pick" : belowFloor ? "below xP floor" : "";
            return (
              <div
                key={c.element_id}
                className={`grid grid-cols-[1fr_42px_46px_52px] items-center gap-1.5 rounded-lg px-1.5 py-1 text-xs ${
                  isPick ? "bg-emerald-500/10" : ""
                }`}
              >
                <span className="flex min-w-0 flex-col">
                  <span className={`truncate ${isPick ? "font-semibold" : ""}`}>{c.web_name}</span>
                  {verdict && (
                    <span className={`text-[9px] ${isPick ? "text-emerald-600" : "text-black/35 dark:text-white/35"}`}>
                      {verdict}
                    </span>
                  )}
                </span>
                <span className="text-right tabular-nums text-black/55 dark:text-white/55">{c.xp.toFixed(1)}</span>
                <span className="text-right tabular-nums text-black/40 dark:text-white/40">{c.ownership.toFixed(0)}%</span>
                <span className={`text-right tabular-nums ${isPick ? "font-semibold" : ""}`}>{capScore(c).toFixed(2)}</span>
              </div>
            );
          })}
          <p className="mt-1.5 px-1.5 text-[10px] leading-relaxed text-black/40 dark:text-white/40">
            xP floor {floor.toFixed(1)} = 80% of the best XI xP (differential-captain index, α = 0.8).
            EO = ownership ÷ 100. Rank-adjusted rewards a high-xP pick the field isn&apos;t piling on.
          </p>
        </div>
      </div>
    </div>
  );
}
