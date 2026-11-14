"use client";
// The one player sheet, opened from every page that lists players.
//
// It used to be two components that had drifted apart: the Predictions sheet and a squad sheet
// labelled "x_minutes", "capt. score" and "λ 2.4/1.0". Now one layout serves both, in the
// site's order of detail. The first screen answers "how many points, and against whom": the
// header, three numbers and the next five fixtures. Everything else (the season so far, why
// the number is what it is, ownership, form and price, and from a squad the legal swaps) sits
// in sections that open on tap, each with its headline on the right so most people never need
// to open them.
//
// The row that opened the sheet carries the scalars, so it renders complete at once; the
// heavier fields (breakdown, form, price, the season so far) arrive from the API a beat later.

import { useEffect, useState } from "react";
import {
  getPlayerDetail,
  type Availability,
  type Prediction,
  type PredictionFixture,
  type SetPieces,
} from "@/lib/api";
import { fdrColour, fdrGlyph, getClub } from "@/lib/clubs";
import { BAND_BLURB, BAND_RANGE, bandStyle } from "@/lib/risk";
import { Jersey } from "@/components/jersey";
import { Fold } from "@/components/fold";
import { Sheet, SheetClose } from "@/components/sheet";
import { SeasonHistory, oppLabel, seasonTotals } from "@/components/season-history";

/** What any list row can hand the sheet. Prediction rows and squad players both fit. */
export type SheetPlayer = {
  element_id: number;
  web_name: string;
  position: "GK" | "DEF" | "MID" | "FWD";
  team: string | null;
  price: number;
  ownership: number;
  xp: number;
  xp_next3?: number;
  x_minutes?: number;
  availability: Availability;
  set_pieces: SetPieces;
  fixtures?: PredictionFixture[];
};

export type SwapOption = {
  other: { element_id: number; web_name: string; position: string; xp: number };
  delta: number;
  apply: () => void;
};

const ORDINAL = ["", "first", "2nd", "3rd", "4th", "5th"];

function Tile({ label, value, emerald = false }: { label: string; value: string; emerald?: boolean }) {
  return (
    <div className="flex flex-col gap-1 rounded-[12px] border border-[var(--line)] px-3 py-2.5">
      <span
        className="t-title text-[20px] font-bold leading-none tabular-nums"
        style={emerald ? { color: "var(--emerald-text)" } : undefined}
      >
        {value}
      </span>
      <span className="text-[12px] text-muted">{label}</span>
    </div>
  );
}

function Line({ label, sub, value, strong = false }: { label: string; sub?: string; value: string; strong?: boolean }) {
  return (
    <div className={`flex items-baseline justify-between gap-3 py-1.5 ${strong ? "" : "border-b border-[var(--line)]"}`}>
      <span className="flex min-w-0 flex-col">
        <span className={`text-[13px] ${strong ? "font-semibold" : ""}`}>{label}</span>
        {sub && <span className="text-[12px] text-muted">{sub}</span>}
      </span>
      <span
        className={`flex-none tabular-nums ${strong ? "text-[15px] font-bold" : "text-[13px] font-semibold"}`}
        style={strong ? { color: "var(--emerald-text)" } : undefined}
      >
        {value}
      </span>
    </div>
  );
}

const pct = (p: number) => `${Math.round(p * 100)}%`;

export function PlayerSheet({
  player,
  gw,
  role,
  swap,
  onClose,
}: {
  player: SheetPlayer;
  /** The gameweek whose projection this is; keys the detail fetch. */
  gw: number | undefined;
  /** Set when opened from a squad, so the header can say "captain" or "bench". */
  role?: "captain" | "starter" | "bench";
  /** Opened from a squad: the legal swaps for this player and what each does to the total. */
  swap?: { title: string; options: SwapOption[] };
  onClose: () => void;
}) {
  const club = getClub(player.team);
  const [detail, setDetail] = useState<Prediction | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (gw == null) return;
    let cancelled = false;
    getPlayerDetail(gw, player.element_id)
      .then((d) => { if (!cancelled) setDetail(d); })
      .catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; };
  }, [gw, player.element_id]);

  const fixtures = detail?.fixtures ?? player.fixtures ?? [];
  const next3 = detail?.xp_next3 ?? player.xp_next3;
  const minutes = detail?.x_minutes ?? player.x_minutes;
  const a = player.availability;
  const flagged = a.status != null && a.status !== "a";
  const pending = failed ? "Couldn't load" : "Loading…";

  const duties = (
    [["Penalties", player.set_pieces.penalties], ["Corners", player.set_pieces.corners], ["Free kicks", player.set_pieces.freekicks]] as const
  ).filter(([, n]) => n != null) as [string, number][];

  const history = detail?.history;
  const totals = history ? seasonTotals(history) : null;
  const b = detail?.breakdown ?? null;
  const isDef = player.position === "GK" || player.position === "DEF";
  const f2 = (n: number) => n.toFixed(2);
  const bestSwap = swap?.options[0];

  return (
    <Sheet onClose={onClose} label={`${player.web_name}, player detail`} className="lg:max-w-[520px] lg:rounded-[20px]">
      {(dismiss) => (
        <>
          {/* who */}
          <div className="flex items-start justify-between gap-3">
            <div className="flex min-w-0 items-center gap-3">
              <Jersey primary={club.primary} secondary={club.secondary} pattern={club.pattern} width={36} height={34} className="block flex-none" />
              <div className="flex min-w-0 flex-col gap-0.5">
                <span className="t-title truncate text-[18px] font-semibold">{player.web_name}</span>
                <span className="text-[13px] text-muted">
                  {player.position} · {player.team} · £{player.price.toFixed(1)}m · {player.ownership.toFixed(1)}% owned
                  {role ? ` · ${role}` : ""}
                </span>
              </div>
            </div>
            <SheetClose onClick={dismiss} />
          </div>

          {duties.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {duties.map(([label, n]) => (
                <span
                  key={label}
                  className={`rounded-full border px-2.5 py-1 text-[12px] font-semibold ${
                    n === 1 ? "border-[var(--emerald-deep)] bg-[var(--emerald-deep)] text-white" : "border-[var(--line)]"
                  }`}
                >
                  {n === 1 ? label : `${label} · ${ORDINAL[n] ?? `${n}th`}`}
                </span>
              ))}
            </div>
          )}

          {/* availability, only when FPL has flagged him: the explanation for a number that would
              otherwise look broken. The factor has already been applied upstream. */}
          {flagged && (
            <div className="flex flex-col gap-1 rounded-[12px] border border-[var(--amber-br)] bg-[var(--amber-bg)] px-3 py-2.5">
              <span className="text-[13px] font-semibold text-[var(--amber-fg)]">
                {a.factor === 0
                  ? `${a.label ?? "Unavailable"}: projected to miss this gameweek`
                  : `${a.label ?? "Doubtful"}: ${a.chance != null ? `${a.chance}% chance to play` : "minutes reduced"}`}
              </span>
              {a.news && <span className="text-[12px] leading-relaxed">{a.news}</span>}
              <span className="text-[12px] text-muted">The projection already allows for this.</span>
            </div>
          )}

          {/* the answer */}
          <div className="grid grid-cols-3 gap-2">
            <Tile label={`xP GW${gw ?? ""}`} value={player.xp.toFixed(1)} emerald />
            <Tile label="next 3 GWs" value={next3 != null ? next3.toFixed(1) : "–"} />
            <Tile label="expected minutes" value={minutes != null ? `${Math.round(minutes)}′` : "–"} />
          </div>

          {fixtures.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <span className="text-[12px] text-muted">Next {Math.min(fixtures.length, 5)} · home in capitals</span>
              <div className="grid grid-cols-5 gap-1.5">
                {fixtures.slice(0, 5).map((f) => {
                  const c = fdrColour(f.fdr);
                  return (
                    <div
                      key={`${f.gw}-${f.opp}`}
                      title={`GW${f.gw} v ${f.opp} (${f.home ? "home" : "away"}), difficulty ${f.fdr} of 5`}
                      className="flex flex-col items-center gap-0.5 rounded-[10px] px-0.5 py-1.5"
                      style={{ background: `color-mix(in oklab, ${c} 16%, transparent)` }}
                    >
                      <span className="text-[11px] tabular-nums text-muted">GW{f.gw}</span>
                      <span className="flex items-center gap-1">
                        <span className="font-mono text-[12px] font-semibold">{oppLabel(f.opp, f.home)}</span>
                        <span
                          className="grid h-4 min-w-4 place-items-center rounded-[4px] px-0.5 text-[10px] font-bold tabular-nums"
                          style={{ background: c, color: fdrGlyph(f.fdr) }}
                        >
                          {f.fdr}
                        </span>
                      </span>
                      <span className="text-[14px] font-bold tabular-nums">{f.xp.toFixed(1)}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* the working, one tap away */}
          <div className="flex flex-col">
            {swap && (
              <Fold
                title={swap.title}
                aside={bestSwap ? `best ${bestSwap.delta >= 0 ? "+" : ""}${bestSwap.delta.toFixed(1)}` : "none"}
                defaultOpen
              >
                {swap.options.length > 0 ? (
                  <div className="flex flex-col gap-1.5">
                    {swap.options.map((o) => (
                      <button
                        key={o.other.element_id}
                        onClick={o.apply}
                        className="press flex min-h-11 items-center justify-between gap-2.5 rounded-[11px] border border-[var(--line)] px-3 py-2 text-left hover:border-emerald-600"
                      >
                        <span className="flex min-w-0 items-center gap-2">
                          <span className="text-[12px] font-semibold text-muted">{o.other.position}</span>
                          <span className="truncate text-[14px] font-semibold">{o.other.web_name}</span>
                          <span className="text-[12px] tabular-nums text-muted">{o.other.xp.toFixed(1)} xP</span>
                        </span>
                        <span
                          className="flex-none text-[13px] font-semibold tabular-nums"
                          style={{ color: o.delta >= 0 ? "var(--emerald-text)" : "var(--rose)" }}
                        >
                          {o.delta >= 0 ? "+" : ""}{o.delta.toFixed(2)}
                        </span>
                      </button>
                    ))}
                    <p className="text-[12px] text-muted">The number is the change to your projected points. Only swaps that keep a legal XI are listed.</p>
                  </div>
                ) : (
                  <p className="text-[13px] text-muted">No swap keeps a legal XI for this player.</p>
                )}
              </Fold>
            )}

            <Fold
              title="Season so far"
              aside={
                detail == null ? pending
                  : !history?.length ? "Nothing yet"
                  : totals && totals.n > 0 ? `${totals.predicted.toFixed(1)} predicted · ${totals.scored} scored`
                  : "Not projected"
              }
            >
              {detail == null ? (
                <p className="text-[13px] text-muted">{pending}</p>
              ) : history?.length ? (
                <SeasonHistory weeks={history} />
              ) : (
                <p className="text-[13px] text-muted">A gameweek appears here once FPL has finalised its points.</p>
              )}
            </Fold>

            <Fold title={`Why ${player.xp.toFixed(1)} xP`}>
              {b ? (
                <div className="flex flex-col">
                  <Line label="Playing time" sub={`plays 60+ minutes: ${pct(b.p_60)}`} value={f2(b.appearance)} />
                  {b.goal_points > 0.001 && <Line label="Goals" sub={`${b.x_goals.toFixed(2)} expected`} value={f2(b.goal_points)} />}
                  {b.assist_points > 0.001 && <Line label="Assists" sub={`${b.x_assists.toFixed(2)} expected`} value={f2(b.assist_points)} />}
                  {b.cs_points > 0.001 && <Line label="Clean sheet" sub={`${pct(b.p_clean_sheet)} chance`} value={f2(b.cs_points)} />}
                  {isDef && <Line label="Goals conceded" sub={`opponent expected to score ${b.opp_lambda.toFixed(1)}`} value={f2(b.conceded_points)} />}
                  {player.position === "GK" && <Line label="Saves" sub={`${b.x_saves.toFixed(1)} expected`} value={f2(b.save_points)} />}
                  {b.dc_points > 0.001 && <Line label="Defensive contribution" sub={`${pct(b.p_dc_point)} chance`} value={f2(b.dc_points)} />}
                  <Line label="Bonus" value={f2(b.bonus_points)} />
                  <Line label="Total" value={b.total.toFixed(2)} strong />
                  <p className="mt-1 text-[12px] text-muted">Each line is the average points from that way of scoring. They add up to the total.</p>
                </div>
              ) : (
                <p className="text-[13px] text-muted">{gw == null ? "No fixture this gameweek." : pending}</p>
              )}
            </Fold>

            <Fold title="Ownership and risk" aside={detail ? detail.risk_label : `${player.ownership.toFixed(0)}% owned`}>
              {detail ? (
                <div className="flex flex-col gap-2.5">
                  {(() => {
                    const bs = bandStyle(detail.risk_tier);
                    return (
                      <div className="flex items-center gap-3 rounded-[12px] border px-3 py-2.5" style={{ background: bs.bg, color: bs.fg, borderColor: bs.border }}>
                        <span className="text-[24px] font-bold leading-none tabular-nums">{detail.risk_tier}</span>
                        <span className="flex min-w-0 flex-col gap-0.5">
                          <span className="text-[13px] font-semibold">{detail.risk_label} · {BAND_RANGE[detail.risk_tier]} owned</span>
                          <span className="text-[12px] leading-snug">{BAND_BLURB[detail.risk_tier]}</span>
                        </span>
                      </div>
                    );
                  })()}
                  <p className="text-[13px] leading-relaxed">
                    Owning him gains you <strong className="tabular-nums">+{detail.diff_value.toFixed(1)}</strong> points on the average manager; not owning him costs you{" "}
                    <strong className="tabular-nums">{detail.template_risk.toFixed(1)}</strong>.
                    As captain, he&apos;d gain you <strong className="tabular-nums">+{detail.captain_score.toFixed(1)}</strong>{" "}on a rival who doesn&apos;t own him.
                  </p>
                  <p className="text-[12px] text-muted">The band comes from ownership alone. It says how contrarian a pick is, not how good.</p>
                </div>
              ) : (
                <p className="text-[13px] text-muted">{pending}</p>
              )}
            </Fold>

            <Fold
              title="Form and price"
              aside={detail ? `form ${detail.recent.form.toFixed(1)}` : undefined}
              className="border-b"
            >
              {detail ? (
                <div className="flex flex-col gap-1.5 text-[13px]">
                  <span>
                    {detail.recent.form === 0
                      ? "No form yet: it starts after the first gameweek."
                      : `${detail.recent.form.toFixed(1)} points per match over the last 30 days.`}
                  </span>
                  <span>
                    {detail.price_moves.change_start === 0 && detail.price_moves.net_transfers === 0
                      ? "His price hasn't moved."
                      : `${detail.price_moves.change_start >= 0 ? "+" : "−"}£${Math.abs(detail.price_moves.change_start).toFixed(1)}m since the season began · net transfers ${detail.price_moves.net_transfers.toLocaleString()} this gameweek`}
                  </span>
                </div>
              ) : (
                <p className="text-[13px] text-muted">{pending}</p>
              )}
            </Fold>
          </div>
        </>
      )}
    </Sheet>
  );
}
