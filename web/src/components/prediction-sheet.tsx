"use client";
// Sheet opened when a prediction row is tapped: five stat tiles, the next-5 fixtures with
// true FDR, and the exact per-term xP breakdown (terms sum to xP). Bottom sheet on mobile,
// centred dialog on desktop. Closes on backdrop / ✕ / Escape.

import { useEffect } from "react";
import type { Prediction } from "@/lib/api";
import { fdrColour, fdrGlyph, getClub } from "@/lib/clubs";
import { BAND_BLURB, BAND_RANGE, bandStyle } from "@/lib/risk";
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
  const a = player.availability;
  const flagged = a.status !== "a";
  const bs = bandStyle(player.risk_tier);

  // First choice = solid emerald-800 + white (7.0:1). Emerald-600 on a tint measured 3.34:1 —
  // illegible for the badge this page most needs to land.
  const duty = (n: number | null, label: string) =>
    n == null ? null : {
      label: `${label} · ${n === 1 ? "first" : n === 2 ? "2nd" : `${n}rd`} choice`,
      border: n === 1 ? "var(--emerald-deep)" : "var(--b10)",
      bg: n === 1 ? "var(--emerald-deep)" : "transparent",
      fg: n === 1 ? "#ffffff" : "var(--fg)",
    };
  const duties = [
    duty(player.set_pieces.penalties, "Penalties"),
    duty(player.set_pieces.corners, "Corners"),
    duty(player.set_pieces.freekicks, "Free kicks"),
  ].filter((d): d is NonNullable<typeof d> => d !== null);
  if (!duties.length) {
    duties.push({ label: "No listed set-piece duty", border: "var(--b10)", bg: "transparent", fg: "var(--fg)" });
  }

  // Preseason: both of these are structurally zero for every player until the first deadline.
  // Say "not yet" rather than implying the player has no form / no price movement.
  const formNote = player.recent.form === 0
    ? "Not yet measured — form is 0.0 for every player until the season starts, and lights up on its own after the first deadline."
    : `Form ${player.recent.form.toFixed(1)} points per match over the last 30 days.`;
  const priceNote = player.price_moves.change_start === 0 && player.price_moves.net_transfers === 0
    ? "Nothing yet — prices don't move before the first deadline. When they do, this shows what HAS happened; there is no price-change forecast here."
    : `£${player.price_moves.change_start.toFixed(1)}m since the season began · net transfers ${player.price_moves.net_transfers.toLocaleString()}`;

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

        {/* availability — the explanation for a number that would otherwise look broken.
            `factor` has ALREADY been applied to xp and x_minutes by the minutes model; this
            block says so, and nothing here re-applies it. */}
        {flagged ? (
          <div className="flex flex-col gap-1 rounded-[12px] border border-[var(--amber-br)] bg-[var(--amber-bg)] px-3 py-2.5">
            <span className="text-[13px] font-semibold text-[var(--amber-fg)]">
              {a.factor === 0
                ? `${a.label ?? "unavailable"} — projection already zeroed`
                : `${a.label ?? "doubtful"} — ${a.chance != null ? `${a.chance}% chance to play` : "reduced minutes"}`}
            </span>
            <span className="text-[11px] leading-relaxed text-black/55 dark:text-white/60">
              {a.factor === 0
                ? `This is why the number reads ${player.xp.toFixed(2)} xP: availability multiplied his expected minutes by 0, so the model has already removed him. Nothing is missing.`
                : `His expected minutes were multiplied by ${a.factor.toFixed(2)} before xP was computed, so this projection is already discounted — it is not an un-flagged risk.`}
            </span>
            {a.news && (
              <span className="text-[11px] leading-relaxed text-black/55 dark:text-white/60">{a.news}</span>
            )}
          </div>
        ) : (
          // the absence of a flag is also worth explaining
          <span className="text-[11px] text-black/55 dark:text-white/60">
            Available — no discount applied (factor {a.factor.toFixed(2)}).
          </span>
        )}

        {/* risk band */}
        <div
          className="flex items-center gap-3 rounded-[12px] border px-3 py-2.5"
          style={{ background: bs.bg, color: bs.fg, borderColor: bs.border }}
        >
          <span className="text-[26px] font-bold leading-none tabular-nums">{player.risk_tier}</span>
          <span className="flex min-w-0 flex-col gap-0.5">
            <span className="text-[13px] font-semibold">
              {player.risk_label} · {BAND_RANGE[player.risk_tier]} owned
            </span>
            <span className="text-[11px] leading-snug">{BAND_BLURB[player.risk_tier]}</span>
          </span>
        </div>

        {/* against the average manager — the raw points-vs-field numbers, in words */}
        <div className="flex flex-col gap-1">
          <span className="text-[10px] font-semibold uppercase tracking-[.07em] text-black/55 dark:text-white/60">
            Against the average manager
          </span>
          <span className="text-[13px] font-semibold">
            Owning him gains +{player.diff_value.toFixed(1)} pts on the average manager.
          </span>
          <span className="text-[13px] font-semibold">
            Not owning him costs you {player.template_risk.toFixed(1)} pts.
          </span>
          <span className="text-[11px] leading-relaxed text-black/55 dark:text-white/60">
            The two always add up to his {player.xp.toFixed(2)} xP — that is the whole trade-off:
            the less the field owns him, the more of his points are yours alone.
          </span>
        </div>

        {/* tiles — `diff value` moved into the sentences above, so no bare float remains */}
        <div className="grid grid-cols-4 gap-1.5">
          <Tile label={`xP GW${gw ?? ""}`} value={player.xp.toFixed(1)} emerald />
          <Tile label="next 3" value={player.xp_next3.toFixed(1)} />
          <Tile label="expected minutes" value={`${Math.round(player.x_minutes)}′`} />
          <Tile label="captain upside" value={f2(player.captain_score)} />
        </div>

        {/* set-piece duty */}
        <div className="flex flex-col gap-1.5">
          <span className="text-[10px] font-semibold uppercase tracking-[.07em] text-black/55 dark:text-white/60">
            Set-piece duty
          </span>
          <div className="flex flex-wrap gap-1.5">
            {duties.map((d) => (
              <span
                key={d.label}
                className="rounded-full border px-2.5 py-1 text-[11px] font-semibold"
                style={{ background: d.bg, color: d.fg, borderColor: d.border }}
              >
                {d.label}
              </span>
            ))}
          </div>
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
                    <span className="w-full rounded-[4px] py-px text-center text-[9px] font-bold" style={{ background: c, color: fdrGlyph(f.fdr) }}>
                      {f.fdr}
                    </span>
                    <span className="text-xs font-bold tabular-nums">{f.xp.toFixed(1)}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* recent form + price momentum — both structurally empty in preseason */}
        <div className="grid grid-cols-1 gap-1.5 lg:grid-cols-2">
          {[["Recent form", formNote], ["Price momentum", priceNote]].map(([title, note]) => (
            <div key={title} className="flex flex-col gap-0.5 rounded-[12px] border border-black/[.06] px-2.5 py-2 dark:border-white/[.06]">
              <span className="text-[10px] font-semibold uppercase tracking-[.07em] text-black/55 dark:text-white/60">
                {title}
              </span>
              <span className="text-[11px] leading-relaxed text-black/55 dark:text-white/60">{note}</span>
            </div>
          ))}
        </div>

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
