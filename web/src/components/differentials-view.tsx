"use client";
// Differentials: presets -> filters -> ONE flat ranked list -> tap for detail.
//
// The risk band is the row's anchor, because `diff_value` and `template_risk` are correct for
// ranking but unreadable as display — "4.48" has no scale and no direction. The band says the
// same thing on 1-5 with a name; the raw points-vs-field numbers move into the sheet as plain
// sentences, so no bare float ever appears in a row.
//
// The list is FLAT, never grouped by band: the band comes from ownership alone, so grouping by
// it would imply a quality hierarchy that does not exist and would bury a strong band-3 pick
// under a stack of sub-2%-owned noise. The band multi-select gives grouping's benefit on
// demand — deselect bands 1-2 and the list IS the differential group, still ranked honestly.

import { useMemo, useState } from "react";
import type { PredictionRow as Prediction } from "@/lib/api";
import { getClub } from "@/lib/clubs";
import { BAND_RANGE, bandStyle, bandTitle } from "@/lib/risk";
import { Jersey } from "@/components/jersey";
import { DEFAULT_PAGE_SIZE, Pagination, pageOf, type PageSize } from "@/components/pagination";
import { PredictionSheet } from "@/components/prediction-sheet";

type Horizon = "xp" | "xp_next3" | "xp_next8";
type Metric = "diff" | "xp" | "value" | "captain";
type Pos = "ALL" | "GK" | "DEF" | "MID" | "FWD";

type Filters = {
  q: string; pos: Pos; bands: number[]; xpFloor: number; minMinutes: number;
  priceMin: number; priceMax: number; team: string; hideFlagged: boolean;
  pensOnly: boolean; horizon: Horizon; metric: Metric;
};

const DEFAULTS: Filters = {
  q: "", pos: "ALL", bands: [1, 2, 3, 4, 5], xpFloor: 3.5, minMinutes: 0,
  priceMin: 4, priceMax: 16, team: "ALL", hideFlagged: false, pensOnly: false,
  horizon: "xp", metric: "diff",
};

const TIERS = [1, 2, 3, 4, 5];
const POSITIONS: Pos[] = ["ALL", "GK", "DEF", "MID", "FWD"];

const PILL = "press min-h-[30px] cursor-pointer rounded-full border px-2.5 py-[5px] text-xs font-semibold";
const PILL_ON = "border-emerald-600 bg-emerald-600 text-white";
const PILL_OFF = "border-black/10 text-black/55 dark:border-white/10 dark:text-white/60";
const LABEL = "t-label text-[10px] text-black/55 dark:text-white/60";
const MUTED = "text-black/55 dark:text-white/60";

const eo = (p: Prediction) => Math.max(0, Math.min(p.ownership / 100, 1));
// xp_next8 is a row scalar computed in toRow BEFORE the fixture list is trimmed to the 3 the
// strip shows. Summing p.fixtures here is the bug this replaced: it silently ranked "Next 8"
// on a next-3 window from the day the trim was added.
const hzXp = (p: Prediction, h: Horizon) =>
  h === "xp_next3" ? p.xp_next3 : h === "xp_next8" ? p.xp_next8 : p.xp;

// --- legend -------------------------------------------------------------------------- //
function RiskBandLegend({ labels }: { labels: Record<number, string> }) {
  return (
    <section className="flex flex-col gap-2.5 rounded-2xl border border-black/10 px-3.5 py-3 shadow-sm dark:border-white/10">
      <div className="flex flex-wrap items-center gap-1.5">
        {TIERS.map((t) => {
          const bs = bandStyle(t);
          return (
            <span
              key={t}
              className="flex items-center gap-1.5 rounded-[9px] border px-2.5 py-1 text-[11px] font-semibold"
              style={{ background: bs.bg, color: bs.fg, borderColor: bs.border }}
            >
              <span className="text-xs font-bold tabular-nums">{t}</span>
              <span>{labels[t]}</span>
              {/* no opacity here: at 11px this is text, and .85 pushed bands 3-4 to 4.43:1 */}
              <span className="font-normal tabular-nums">{BAND_RANGE[t]}</span>
            </span>
          );
        })}
      </div>
      <p className={`text-xs leading-[1.55] ${MUTED}`}>
        The band comes from <strong className="font-semibold text-[var(--fg)]">ownership alone</strong>.
        A 9-xP star and a 0.5-xP bench player on the same ownership sit in the same band — it tells
        you how contrarian a pick is,{" "}
        <strong className="font-semibold text-[var(--fg)]">never how good</strong>. Quality is xP and
        the xP floor below. The ramp deliberately runs neutral → deep emerald rather than reusing the
        fixture green-to-red: on the Fixtures page green means &ldquo;easy&rdquo;, and a red band 5
        would read as &ldquo;bad player&rdquo; when a deep punt is the whole point of this page.
      </p>
    </section>
  );
}

// --- presets ------------------------------------------------------------------------- //
const PRESETS: { name: string; label: string; sub: string; patch: Partial<Filters> }[] = [
  { name: "budget", label: "Budget enablers", sub: "under £5.5m, ranked per £m",
    patch: { priceMax: 5.5, bands: [3, 4, 5], metric: "value" } },
  { name: "run", label: "Best next-8 run", sub: "eight-gameweek total, low owned",
    patch: { horizon: "xp_next8", bands: [3, 4, 5], xpFloor: 12, metric: "diff" } },
  { name: "pens", label: "Penalty-taking punts", sub: "first-choice takers, band 3–5",
    patch: { pensOnly: true, bands: [3, 4, 5], metric: "diff" } },
  { name: "deep", label: "Deep punts only", sub: "band 5 — under 2% owned",
    patch: { bands: [5], metric: "diff" } },
];

function PresetRow({ active, apply }: { active: string | null; apply: (n: string, p: Partial<Filters>) => void }) {
  return (
    <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
      {PRESETS.map((d) => {
        const on = active === d.name;
        return (
          <button
            key={d.name}
            onClick={() => apply(d.name, d.patch)}
            className={`press flex cursor-pointer flex-col gap-0.5 rounded-[12px] border px-3 py-2.5 text-left ${
              on ? "border-emerald-600 bg-emerald-600" : "border-black/10 dark:border-white/10"
            }`}
          >
            <span className={`text-[13px] font-semibold ${on ? "text-white" : ""}`}>{d.label}</span>
            <span className={`text-[11px] leading-snug ${on ? "text-white" : MUTED}`}>{d.sub}</span>
          </button>
        );
      })}
    </div>
  );
}

// --- filters ------------------------------------------------------------------------- //
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className={LABEL}>{label}</span>
      {children}
    </label>
  );
}

/** Constraints a preset can switch on that have no visible control of their own. Without
 *  these chips they would keep filtering silently once the preset marker clears — the list
 *  would be narrowed by something the page never mentions. */
function activeConstraints(f: Filters, patch: (o: Partial<Filters>) => void) {
  const out: { label: string; clear: () => void }[] = [];
  if (f.pensOnly) out.push({ label: "penalty takers only", clear: () => patch({ pensOnly: false }) });
  if (f.priceMax !== DEFAULTS.priceMax) out.push({ label: `under £${f.priceMax.toFixed(1)}m`, clear: () => patch({ priceMax: DEFAULTS.priceMax }) });
  if (f.priceMin !== DEFAULTS.priceMin) out.push({ label: `over £${f.priceMin.toFixed(1)}m`, clear: () => patch({ priceMin: DEFAULTS.priceMin }) });
  if (f.minMinutes > 0) out.push({ label: `${f.minMinutes}′+ expected`, clear: () => patch({ minMinutes: 0 }) });
  if (f.team !== "ALL") out.push({ label: f.team, clear: () => patch({ team: "ALL" }) });
  if (f.hideFlagged) out.push({ label: "flagged hidden", clear: () => patch({ hideFlagged: false }) });
  return out;
}

function FilterPanel({
  f, patch, bandCounts, bandLabels, hzTag,
}: {
  f: Filters; patch: (o: Partial<Filters>) => void;
  bandCounts: Record<number, number>; bandLabels: Record<number, string>;
  hzTag: string;
}) {
  const constraints = activeConstraints(f, patch);
  return (
    <section className="flex flex-col gap-2.5 rounded-2xl border border-black/10 px-3.5 py-3 shadow-sm dark:border-white/10">
      {/* row 1 — the two most-used controls stay visible on a phone */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex gap-1.5">
          {POSITIONS.map((p) => (
            <button key={p} onClick={() => patch({ pos: p })} className={`${PILL} ${f.pos === p ? PILL_ON : PILL_OFF}`}>
              {p}
            </button>
          ))}
        </div>
        <input
          value={f.q}
          onChange={(e) => patch({ q: e.target.value })}
          placeholder="Search player or club"
          className="min-h-[30px] min-w-[160px] flex-1 rounded-full border border-black/10 bg-transparent px-3 py-[5px] text-xs dark:border-white/10"
        />
      </div>

      {/* row 2 — band multi-select, each chip counting what WOULD pass if it were on */}
      <div className="flex flex-wrap items-center gap-1.5">
        {TIERS.map((t) => {
          const on = f.bands.includes(t);
          const bs = bandStyle(t);
          return (
            <button
              key={t}
              aria-pressed={on}
              title={bandTitle(t, bandLabels[t])}
              onClick={() => patch({ bands: on ? f.bands.filter((x) => x !== t) : [...f.bands, t].sort() })}
              // inactive falls back to the standard inactive pill — as utility classes, not an
              // inline colour, so it still flips with the theme
              className={`press flex min-h-[30px] cursor-pointer items-center gap-1.5 rounded-full border px-2.5 py-[5px] text-[11px] font-semibold ${
                on ? "" : PILL_OFF
              }`}
              style={on ? { background: bs.bg, color: bs.fg, borderColor: bs.border } : undefined}
            >
              <span className="text-xs font-bold tabular-nums">{t}</span>
              <span>{bandLabels[t]}</span>
              <span className="font-normal tabular-nums">{bandCounts[t] ?? 0}</span>
            </button>
          );
        })}
      </div>

      {/* row 3 — the two controls that change the answer most */}
      <div className="grid grid-cols-[repeat(auto-fit,minmax(210px,1fr))] gap-2.5">
        <Field label={`${hzTag} floor · ${f.xpFloor.toFixed(1)}`}>
          <input
            type="range" min={0} max={20} step={0.5} value={f.xpFloor}
            onChange={(e) => patch({ xpFloor: Number(e.target.value) })}
            className="accent-emerald-600"
          />
        </Field>
        <Field label="horizon">
          <div className="flex gap-1.5">
            {([["xp", "This GW"], ["xp_next3", "Next 3"], ["xp_next8", "Next 8"]] as const).map(([h, l]) => (
              <button key={h} onClick={() => patch({ horizon: h })} className={`${PILL} ${f.horizon === h ? PILL_ON : PILL_OFF}`}>
                {l}
              </button>
            ))}
          </div>
        </Field>
      </div>

      {/* whatever a preset switched on beyond these controls, stated and dismissible */}
      {constraints.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className={LABEL}>also applied</span>
          {constraints.map((c) => (
            <button
              key={c.label}
              onClick={c.clear}
              title={`Remove: ${c.label}`}
              className={`${PILL} ${PILL_OFF} flex items-center gap-1.5`}
            >
              {c.label}
              <span aria-hidden className="text-[13px] leading-none">×</span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

// --- rank-by ------------------------------------------------------------------------- //
const METRIC_LABEL: [Metric, string][] = [
  ["diff", "Points gained on the field"],
  ["xp", "Raw xP"],
  ["value", "Value per £m"],
  ["captain", "Captain upside"],
];

function RankByPills({ metric, patch }: { metric: Metric; patch: (o: Partial<Filters>) => void }) {
  return (
    <div className="flex items-center gap-2 overflow-x-auto">
      <span className={`${LABEL} flex-none`}>rank by</span>
      {METRIC_LABEL.map(([m, l]) => (
        <button key={m} onClick={() => patch({ metric: m })} className={`${PILL} flex-none ${metric === m ? PILL_ON : PILL_OFF}`}>
          {l}
        </button>
      ))}
    </div>
  );
}

// --- one row ------------------------------------------------------------------------- //
function PlayerRow({
  p, rank, horizon, metricLine, hzUnit, onOpen,
}: {
  p: Prediction; rank: number; horizon: Horizon; metricLine: string; hzUnit: string;
  onOpen: (p: Prediction) => void;
}) {
  const club = getClub(p.team);
  const bs = bandStyle(p.risk_tier);
  const a = p.availability;
  const flagged = a.status !== "a";

  return (
    <li
      onClick={() => onOpen(p)}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onOpen(p)}
      role="button"
      tabIndex={0}
      className="press flex min-h-[60px] cursor-pointer items-center gap-2 border-b border-black/[.06] px-2.5 py-2.5 hover:bg-black/[.02] dark:border-white/[.06] dark:hover:bg-white/[.03]"
    >
      <span className="w-[15px] flex-none text-right font-mono text-[10px] tabular-nums text-black/55 dark:text-white/60">
        {rank}
      </span>

      <Jersey primary={club.primary} secondary={club.secondary} pattern={club.pattern} width={24} height={23} className="block flex-none" />

      {/* identity — the only flexible column */}
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <div className="flex min-w-0 flex-wrap items-center gap-1.5">
          <span className="truncate text-sm font-semibold">{p.web_name}</span>
          <span className="flex-none font-mono text-[10px] text-black/55 dark:text-white/60">{club.shortCode}</span>

          {/* set-piece duty: solid emerald-800 + white = 7.0:1. Emerald-600 on a tint
              measured 3.34:1 — illegible for the badge this page most needs to land. */}
          {p.set_pieces.penalties === 1 && (
            <span title="First-choice penalty taker" className="flex-none rounded bg-[var(--emerald-deep)] px-1.5 py-px text-[10px] font-bold text-white">
              PEN 1st
            </span>
          )}

          {/* availability is never colour alone — the chip prints the chance or the label */}
          {flagged && (
            <span
              title={`${a.label ?? ""}${a.news ? ` — ${a.news}` : ""}`}
              className="flex-none rounded bg-[var(--amber-bg)] px-1.5 py-px text-[10px] font-bold text-[var(--amber-fg)]"
            >
              {a.factor > 0 && a.chance != null ? `${a.chance}%` : (a.label ?? "out")}
            </span>
          )}
        </div>

        <span className="text-[11px] tabular-nums text-black/55 dark:text-white/60">
          {p.position} · {p.team} · £{p.price.toFixed(1)} · {p.ownership.toFixed(1)}% owned
        </span>

        {/* the active ranking metric, restated in words — no bare floats */}
        <span className="text-[11px] leading-snug text-black/55 dark:text-white/60">{metricLine}</span>
      </div>

      {/* THE BAND — the row's visual anchor. Digit AND label, always. */}
      <span
        title={bandTitle(p.risk_tier, p.risk_label)}
        className="flex min-h-[38px] w-[78px] flex-none flex-col items-center justify-center rounded-[9px] border px-1 py-0.5"
        style={{ background: bs.bg, color: bs.fg, borderColor: bs.border }}
      >
        <span className="text-[15px] font-bold leading-[1.1] tabular-nums">{p.risk_tier}</span>
        <span className="text-center text-[10px] font-semibold leading-tight">{p.risk_label}</span>
      </span>

      <div className="flex w-11 flex-none flex-col items-end">
        {/* 19px/700 emerald-600 qualifies as large text at 3:1 — smaller emerald must not */}
        <span className="t-title text-[19px] font-bold leading-none tabular-nums text-emerald-600">
          {hzXp(p, horizon).toFixed(1)}
        </span>
        <span className="t-label text-[10px] text-black/55 dark:text-white/60">{hzUnit}</span>
      </div>
    </li>
  );
}

// --- empty state --------------------------------------------------------------------- //
function EmptyState({ reason, fixes, reset }: {
  reason: string; fixes: { label: string; apply: () => void }[]; reset: () => void;
}) {
  return (
    <div className="flex flex-col gap-2.5 rounded-2xl border border-black/10 px-3.5 py-4 dark:border-white/10">
      <p className={`max-w-[52ch] text-[13px] leading-[1.55] ${MUTED}`}>{reason}</p>
      <div className="flex flex-wrap gap-1.5">
        {fixes.map((fx) => (
          <button key={fx.label} onClick={fx.apply} className={`${PILL} ${PILL_OFF}`}>{fx.label}</button>
        ))}
        <button onClick={reset} className={`${PILL} ${PILL_OFF}`}>Reset all filters</button>
      </div>
    </div>
  );
}

// --- the page's one client component -------------------------------------------------- //
export function DifferentialsExplorer({ predictions }: { predictions: Prediction[] }) {
  const [f, setF] = useState<Filters>(DEFAULTS);
  const [activePreset, setActivePreset] = useState<string | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<PageSize>(DEFAULT_PAGE_SIZE);

  // Touching any individual filter clears the preset marker, so an active preset always
  // describes the state exactly. Presets REPLACE the state rather than layering onto it.
  // Both reset to page 1 — changing the filter and staying on page 4 shows a slice of a set
  // the user has never seen the top of.
  const patch = (o: Partial<Filters>) => {
    setF((prev) => ({ ...prev, ...o })); setActivePreset(null); setPage(1);
  };
  const applyPreset = (name: string, p: Partial<Filters>) => {
    setF({ ...DEFAULTS, ...p }); setActivePreset(name); setOpenId(null); setPage(1);
  };

  // The horizon button says "Next 8" (the product's intent) but the unit label states what the
  // payload actually offers, so a shorter payload never claims 8 gameweeks it does not have.
  // Max across ALL rows, never row zero alone: per-row counts legitimately vary — a club with
  // a blank sums 7 real gameweeks and earns nothing in the blank, which is correct ranking —
  // so one club's blank must not relabel every other row's genuine 8-gameweek sum.
  const nGw = predictions.length
    ? Math.max(...predictions.map((p) => p.xp_next8_gws))
    : 8;
  const hzTag = f.horizon === "xp_next3" ? "xP over 3 GW" : f.horizon === "xp_next8" ? `xP over ${nGw} GW` : "xP";
  const hzUnit = f.horizon === "xp_next3" ? "xP · 3gw" : f.horizon === "xp_next8" ? `xP · ${nGw}gw` : "xP";

  const passesExceptBand = useMemo(() => {
    const needle = f.q.trim().toLowerCase();
    return (p: Prediction) =>
      !p.low_coverage &&
      (f.pos === "ALL" || p.position === f.pos) &&
      (needle === "" || p.web_name.toLowerCase().includes(needle) || (p.team ?? "").toLowerCase().includes(needle)) &&
      hzXp(p, f.horizon) >= f.xpFloor &&
      p.x_minutes >= f.minMinutes &&
      p.price >= f.priceMin && p.price <= f.priceMax &&
      (f.team === "ALL" || p.team === f.team) &&
      (!f.hideFlagged || p.availability.status === "a") &&
      (!f.pensOnly || p.set_pieces.penalties === 1);
  }, [f]);

  const metricOf = (p: Prediction) => {
    const x = hzXp(p, f.horizon);
    if (f.metric === "xp") return x;
    if (f.metric === "value") return p.price ? x / p.price : 0;
    if (f.metric === "captain") return 2 * x * (1 - eo(p));
    return x * (1 - eo(p));
  };

  const metricLine = (p: Prediction) => {
    const x = hzXp(p, f.horizon);
    const gain = x * (1 - eo(p));
    if (f.metric === "value") return `${(p.price ? x / p.price : 0).toFixed(2)} ${hzTag} per £m spent`;
    if (f.metric === "captain") return `captained, he gains +${(2 * gain).toFixed(1)} pts on the field`;
    if (f.metric === "xp") return `owning him gains +${gain.toFixed(1)} pts; not owning him costs ${(x * eo(p)).toFixed(1)}`;
    return `owning him gains +${gain.toFixed(1)} pts on the average manager`;
  };

  const rows = useMemo(
    () => predictions.filter((p) => passesExceptBand(p) && f.bands.includes(p.risk_tier))
                     .sort((a, b) => metricOf(b) - metricOf(a)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [predictions, passesExceptBand, f.bands, f.metric, f.horizon],
  );

  // Each band chip counts what WOULD pass if that band were on, so an empty band is visible
  // before you tap it.
  const bandCounts = useMemo(() => {
    const out: Record<number, number> = {};
    for (const t of TIERS) out[t] = predictions.filter((p) => p.risk_tier === t && passesExceptBand(p)).length;
    return out;
  }, [predictions, passesExceptBand]);

  const bandLabels = useMemo(() => {
    const out: Record<number, string> = {};
    for (const t of TIERS) out[t] = predictions.find((p) => p.risk_tier === t)?.risk_label ?? "";
    return out;
  }, [predictions]);

  const pg = pageOf(rows, page, pageSize);
  const open = openId != null ? predictions.find((p) => p.element_id === openId) ?? null : null;

  const rankNote = f.horizon === "xp_next8" && nGw < 8
    ? `One flat ranking, so a strong band-3 pick is never buried under a stack of band-5 noise. Eight-gameweek window requested — this payload carries ${nGw}, so that is what is summed.`
    : "One flat ranking, so a strong band-3 pick is never buried under a stack of band-5 noise.";

  const emptyReason =
    `Nothing passes every filter at once. The ${hzTag} floor of ${f.xpFloor.toFixed(1)} is the usual ` +
    "culprit — it exists so an unowned dud never tops this list" +
    (f.pensOnly ? ", and 'penalty takers only' is a small pool" : "") +
    (f.bands.length < 3 ? ", and you have narrowed the bands" : "") + ".";

  return (
    <div className="flex flex-col gap-3">
      <RiskBandLegend labels={bandLabels} />
      <PresetRow active={activePreset} apply={applyPreset} />
      <FilterPanel f={f} patch={patch} bandCounts={bandCounts} bandLabels={bandLabels} hzTag={hzTag} />
      <RankByPills metric={f.metric} patch={patch} />

      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className={`text-[11px] ${MUTED}`}>{rows.length} of {predictions.length} players match</span>
        <span className={`max-w-[60ch] text-[11px] leading-snug ${MUTED}`}>{rankNote}</span>
      </div>

      {rows.length === 0 ? (
        <EmptyState
          reason={emptyReason}
          fixes={[
            { label: "Drop the floor to 0", apply: () => patch({ xpFloor: 0 }) },
            { label: "All five bands", apply: () => patch({ bands: [1, 2, 3, 4, 5] }) },
          ]}
          reset={() => { setF(DEFAULTS); setActivePreset(null); }}
        />
      ) : (
        <>
          <ul className="overflow-hidden rounded-2xl border border-black/10 shadow-sm dark:border-white/10">
            {pg.slice.map((p, i) => (
              <PlayerRow
                key={p.element_id} p={p} rank={pg.from + i + 1} horizon={f.horizon}
                metricLine={metricLine(p)} hzUnit={hzUnit} onOpen={(x) => setOpenId(x.element_id)}
              />
            ))}
          </ul>
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
