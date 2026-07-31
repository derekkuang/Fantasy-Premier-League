"use client";
// Sheet opened when a prediction row is tapped: five stat tiles, the next-5 fixtures with
// true FDR, and the exact per-term xP breakdown (terms sum to xP). Bottom sheet on mobile,
// centred dialog on desktop. Closes on backdrop / ✕ / Escape.

import { useEffect } from "react";
import type { Prediction } from "@/lib/api";
import { fdrColour, getClub } from "@/lib/clubs";
import { Jersey } from "@/components/jersey";

function Tile({ label, value, emerald = false }: { label: string; value: string; emerald?: boolean }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-[10px] border border-black/[.06] px-2 py-[7px] dark:border-white/[.06]">
      <span className={`text-base font-bold leading-none tabular-nums ${emerald ? "text-emerald-600" : ""}`}>{value}</span>
      <span className="text-[9px] text-black/40 dark:text-white/40">{label}</span>
    </div>
  );
}

function Row({ label, value, negative = false, strong = false }: { label: string; value: string; negative?: boolean; strong?: boolean }) {
  return (
    <div
      className={`flex items-baseline justify-between gap-2 px-0.5 py-[5px] text-xs ${
        strong ? "" : "border-b border-black/[.06] dark:border-white/[.06]"
      }`}
    >
      <span className={strong ? "font-semibold" : "text-black/55 dark:text-white/55"}>{label}</span>
      <span
        className={`tabular-nums ${strong ? "font-bold text-emerald-600" : "font-semibold"}`}
        style={negative ? { color: "#e11d48" } : undefined}
      >
        {value}
      </span>
    </div>
  );
}

export function PredictionSheet({ player, onClose }: { player: Prediction; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const club = getClub(player.team);
  const fixtures = player.fixtures ?? [];
  const gw = fixtures[0]?.gw;
  const b = player.breakdown;
  const f2 = (n: number) => n.toFixed(2);
  const isDef = player.position === "GK" || player.position === "DEF";

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center lg:items-center lg:p-6">
      <div className="absolute inset-0 bg-black/45 backdrop-blur-[2px]" onClick={onClose} />
      <div className="relative flex max-h-[88vh] w-full max-w-[430px] flex-col gap-3.5 overflow-y-auto rounded-t-[20px] border border-black/10 bg-white px-4 pb-6 pt-3.5 shadow-[0_-8px_30px_rgba(0,0,0,.25)] dark:border-white/10 dark:bg-[#0a0a0a] lg:max-w-[560px] lg:rounded-[20px]">
        {/* header */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <Jersey primary={club.primary} secondary={club.secondary} pattern={club.pattern} width={34} height={32} className="block flex-none" />
            <div className="flex flex-col gap-px">
              <span className="text-[17px] font-semibold tracking-[-.01em]">{player.web_name}</span>
              <span className="text-[11px] text-black/40 dark:text-white/40">
                {player.position} · {player.team} · £{player.price.toFixed(1)} · {player.ownership.toFixed(1)}% owned
              </span>
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="grid h-7 w-7 flex-none place-items-center rounded-full border border-black/10 text-black/50 hover:text-black dark:border-white/10 dark:text-white/50 dark:hover:text-white"
          >
            ✕
          </button>
        </div>

        {/* tiles */}
        <div className="grid grid-cols-5 gap-1.5">
          <Tile label={`xP GW${gw ?? ""}`} value={player.xp.toFixed(1)} emerald />
          <Tile label="next 3" value={player.xp_next3.toFixed(1)} />
          <Tile label="x_minutes" value={Math.round(player.x_minutes).toString()} />
          <Tile label="diff value" value={f2(player.diff_value)} />
          <Tile label="capt. score" value={f2(player.captain_score)} />
        </div>

        {/* next 5 fixtures */}
        {fixtures.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <span className="text-[10px] font-semibold uppercase tracking-[.07em] text-black/40 dark:text-white/40">
              Next {Math.min(fixtures.length, 5)} fixtures · true FDR
            </span>
            <div className="grid grid-cols-5 gap-1.5">
              {fixtures.slice(0, 5).map((f) => {
                const c = fdrColour(f.fdr);
                return (
                  <div
                    key={f.gw}
                    className="flex flex-col items-center gap-0.5 rounded-[9px] border border-black/[.06] px-0.5 py-1.5 dark:border-white/[.06]"
                    style={{ background: `color-mix(in oklab, ${c} 14%, transparent)` }}
                  >
                    <span className="text-[9px] tabular-nums text-black/40 dark:text-white/40">GW{f.gw}</span>
                    <span className="font-mono text-[11px] font-semibold">{getClub(f.opp).shortCode}</span>
                    <span className="text-[9px] text-black/40 dark:text-white/40">({f.home ? "H" : "A"})</span>
                    <span className="w-full rounded-[4px] py-px text-center text-[9px] font-bold text-white" style={{ background: c }}>
                      {f.fdr}
                    </span>
                    <span className="text-xs font-bold tabular-nums">{f.xp.toFixed(1)}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* why this xP */}
        {b && (
          <div className="flex flex-col">
            <span className="mb-1 text-[10px] font-semibold uppercase tracking-[.07em] text-black/40 dark:text-white/40">
              Why this xP
            </span>
            <Row label={`appearance · P(60′) ${b.p_60.toFixed(2)}`} value={f2(b.appearance)} />
            {b.goal_points > 0.001 && <Row label={`xG ${b.x_goals.toFixed(2)} × goal points`} value={f2(b.goal_points)} />}
            {b.assist_points > 0.001 && <Row label={`xA ${b.x_assists.toFixed(2)} × 3`} value={f2(b.assist_points)} />}
            {b.cs_points > 0.001 && <Row label={`clean sheet · P ${b.p_clean_sheet.toFixed(2)}`} value={f2(b.cs_points)} />}
            {isDef && <Row label={`goals conceded · vs ${b.opp_lambda.toFixed(1)} xGA`} value={f2(b.conceded_points)} negative />}
            {player.position === "GK" && <Row label={`saves ${b.x_saves.toFixed(1)} ÷ 3`} value={f2(b.save_points)} />}
            {b.dc_points > 0.001 && <Row label={`defensive contribution · P ${b.p_dc_point.toFixed(2)}`} value={f2(b.dc_points)} />}
            <Row label="expected bonus" value={f2(b.bonus_points)} />
            <Row label="total xP" value={b.total.toFixed(2)} strong />
            <p className="mt-1.5 text-[10px] leading-relaxed text-black/40 dark:text-white/40">
              Each term is the mean points from that scoring category; they sum to xP.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
