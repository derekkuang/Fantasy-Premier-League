"use client";
// Bottom sheet shown when a player is tapped. The "Why this xP" section reads the exact
// per-term split the backend now emits (breakdown), so the numbers add up to the player's
// xP rather than being reconstructed. Next-5 fixtures come from the true-FDR ticker.

import { useEffect } from "react";
import { fdrFor, type SquadPlayer, type TickerFixture } from "@/lib/api";
import { fdrColour, getClub } from "@/lib/clubs";
import { Jersey } from "@/components/jersey";

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-[10px] border border-black/[.06] px-2 py-[7px] dark:border-white/[.06]">
      <span className="text-base font-bold leading-none tabular-nums">{value}</span>
      <span className="text-[9px] text-black/40 dark:text-white/40">{label}</span>
    </div>
  );
}

function Row({ label, value, strong = false }: { label: string; value: string; strong?: boolean }) {
  return (
    <div
      className={`flex items-baseline justify-between gap-2 border-b border-black/[.06] px-0.5 py-[5px] text-xs last:border-0 dark:border-white/[.06] ${strong ? "border-0 pt-[7px] text-[13px]" : ""}`}
    >
      <span className={strong ? "font-semibold" : "text-black/55 dark:text-white/55"}>{label}</span>
      <span className={`tabular-nums ${strong ? "font-bold text-emerald-600" : "font-semibold"}`}>{value}</span>
    </div>
  );
}

export type SwapOption = { other: SquadPlayer; delta: number; apply: () => void };

export function PlayerSheet({ player, fixtures, swapTitle, swapOptions, onClose }: {
  player: SquadPlayer;
  fixtures: TickerFixture[];
  swapTitle: string;
  swapOptions: SwapOption[];
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const club = getClub(player.team);
  const b = player.breakdown;
  const role = player.is_captain ? "captain" : player.is_starter ? "starter" : "bench";
  const f2 = (n: number) => n.toFixed(2);

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center">
      <div className="absolute inset-0 bg-black/45 backdrop-blur-[2px]" onClick={onClose} />
      <div className="relative flex max-h-[88vh] w-full max-w-[430px] flex-col gap-3.5 overflow-y-auto rounded-t-[20px] border border-b-0 border-black/10 bg-white px-4 pb-6 pt-3.5 shadow-[0_-8px_30px_rgba(0,0,0,.25)] dark:border-white/10 dark:bg-[#0a0a0a]">
        {/* header */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <Jersey primary={club.primary} secondary={club.secondary} pattern={club.pattern} width={34} height={32} className="block flex-none" />
            <div className="flex flex-col gap-px">
              <span className="text-[17px] font-semibold tracking-[-.01em]">{player.web_name}</span>
              <span className="text-[11px] text-black/40 dark:text-white/40">
                {player.position} · {player.team} · £{player.price.toFixed(1)} · {role}
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

        {/* stat tiles */}
        <div className="grid grid-cols-4 gap-1.5">
          <Tile label="xP" value={player.xp.toFixed(1)} />
          <Tile label="x_minutes" value={player.x_minutes != null ? Math.round(player.x_minutes).toString() : "—"} />
          <Tile label="diff value" value={player.diff_value != null ? f2(player.diff_value) : "—"} />
          <Tile label="capt. score" value={player.captain_score != null ? f2(player.captain_score) : "—"} />
        </div>

        {/* next 5 fixtures */}
        {fixtures.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <span className="text-[10px] font-semibold uppercase tracking-[0.07em] text-black/40 dark:text-white/40">
              Next {Math.min(fixtures.length, 5)} fixtures · true FDR
            </span>
            <div className="grid grid-cols-5 gap-1.5">
              {fixtures.slice(0, 5).map((fx, i) => {
                const fdr = fdrFor(player.position, fx);
                return (
                  <div key={i} className="flex flex-col items-center gap-0.5 rounded-[9px] border border-black/[.06] px-0.5 py-1.5 dark:border-white/[.06]">
                    <span className="text-[9px] tabular-nums text-black/40 dark:text-white/40">GW{fx.gw}</span>
                    <span className="font-mono text-[11px] font-semibold">{getClub(fx.opp).shortCode}</span>
                    <span className="text-[9px] text-black/40 dark:text-white/40">({fx.home ? "H" : "A"})</span>
                    <span className="w-full rounded-[4px] py-px text-center text-[9px] font-bold tabular-nums text-white" style={{ background: fdrColour(fdr) }}>
                      {fdr}
                    </span>
                    <span className="text-[8px] tabular-nums text-black/40 dark:text-white/40">
                      λ {fx.lam_for.toFixed(1)}/{fx.lam_against.toFixed(1)}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* why this xP */}
        {b && (
          <div className="flex flex-col">
            <span className="mb-1 text-[10px] font-semibold uppercase tracking-[0.07em] text-black/40 dark:text-white/40">
              Why this xP
            </span>
            <Row label={`appearance · P(60′) ${b.p_60.toFixed(2)}`} value={f2(b.appearance)} />
            {b.goal_points > 0.001 && <Row label={`xG ${b.x_goals.toFixed(2)} × goal points`} value={f2(b.goal_points)} />}
            {b.assist_points > 0.001 && <Row label={`xA ${b.x_assists.toFixed(2)} × 3`} value={f2(b.assist_points)} />}
            {b.cs_points > 0.001 && <Row label={`clean sheet · P ${b.p_clean_sheet.toFixed(2)}`} value={f2(b.cs_points)} />}
            {(player.position === "GK" || player.position === "DEF") && (
              <Row label={`goals conceded · vs ${b.opp_lambda.toFixed(1)} xGA`} value={f2(b.conceded_points)} />
            )}
            {player.position === "GK" && <Row label={`saves ${b.x_saves.toFixed(1)} ÷ 3`} value={f2(b.save_points)} />}
            {b.dc_points > 0.001 && <Row label="defensive contribution" value={f2(b.dc_points)} />}
            <Row label="expected bonus" value={f2(b.bonus_points)} />
            <Row label="total xP" value={b.total.toFixed(2)} strong />
          </div>
        )}

        {/* legal swaps */}
        <div className="flex flex-col gap-1.5 border-t border-black/[.06] pt-3 dark:border-white/[.06]">
          <span className="text-[10px] font-semibold uppercase tracking-[0.07em] text-black/40 dark:text-white/40">
            {swapTitle}
          </span>
          {swapOptions.length > 0 ? (
            swapOptions.map((o) => (
              <button
                key={o.other.element_id}
                onClick={o.apply}
                className="flex items-center justify-between gap-2.5 rounded-[11px] border border-black/10 px-3 py-2 text-left hover:border-emerald-600 dark:border-white/10"
              >
                <span className="flex min-w-0 items-center gap-1.5">
                  <span className="rounded bg-black/5 px-1.5 py-px text-[9px] font-semibold text-black/50 dark:bg-white/10 dark:text-white/50">
                    {o.other.position}
                  </span>
                  <span className="truncate text-[13px] font-semibold">{o.other.web_name}</span>
                  <span className="tabular-nums text-[11px] text-black/40 dark:text-white/40">{o.other.xp.toFixed(1)} xP</span>
                </span>
                <span
                  className="flex-none text-[11px] font-semibold tabular-nums"
                  style={{ color: o.delta >= 0 ? "#059669" : "#e11d48" }}
                >
                  {o.delta >= 0 ? "+" : ""}
                  {o.delta.toFixed(2)}
                </span>
              </button>
            ))
          ) : (
            <p className="text-[11px] text-black/40 dark:text-white/40">No legal swap for this player.</p>
          )}
          <p className="px-0.5 text-[10px] leading-relaxed text-black/40 dark:text-white/40">
            Only swaps that leave a legal XI (1 GK · 3–5 DEF · 2–5 MID · 1–3 FWD) are offered;
            the delta is the change in projected points. The formation label follows the result.
          </p>
        </div>

        <p className="px-0.5 text-[10px] leading-relaxed text-black/40 dark:text-white/40">
          Every term is the mean points from that scoring category; they sum to the player&apos;s
          xP. Clean-sheet and appearance points are gated by expected minutes.
        </p>
      </div>
    </div>
  );
}
