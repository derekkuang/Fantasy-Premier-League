"use client";
// Pick fifteen players, then get the same dashboard an FPL entry id would have given you.
//
// The entry-id path only works if you know your id and the season has started — before the
// first deadline the FPL API exposes no squads at all, so every real id 404s and the sample
// team is the only thing anyone can look at. This is the way in for everyone else.
//
// Two panes, one job. The squad is always visible with its empty slots showing, because the
// thing you most need to know while picking is what you still need. The picker below defaults
// to whichever position still has a gap, so the common path is: open, tap, tap, tap.

import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import type { Prediction, TeamResponse, TickerFixture } from "@/lib/api";
import { getClub } from "@/lib/clubs";
import { POS_ORDER, countByPos, type Pos } from "@/lib/formation";
import {
  BUDGET,
  SQUAD_QUOTA,
  SQUAD_SIZE,
  autoPick,
  blockedReason,
  buildTeamResponse,
  decodeSquad,
  encodeSquad,
  totalCost,
  violations,
} from "@/lib/squad";
import { Jersey } from "@/components/jersey";
import { TeamDashboard } from "@/components/team-dashboard";

const STORAGE_KEY = "fpledge.squad";

/** The saved draft, read the way React wants a client-only store read.
 *
 *  localStorage doesn't exist on the server, so the obvious "read it in an effect and
 *  setState" produces a cascading render on every mount. `useSyncExternalStore` is the
 *  primitive for exactly this: an empty server snapshot, the real value on the client, and
 *  no extra render pass. The snapshot stays a STRING because the store must return a stable
 *  identity — parsing on every call would hand React a new array each time and spin. */
function useSavedDraft(): number[] {
  const raw = useSyncExternalStore(
    (onChange) => {
      window.addEventListener("storage", onChange);
      return () => window.removeEventListener("storage", onChange);
    },
    () => {
      try {
        return localStorage.getItem(STORAGE_KEY) ?? "[]";
      } catch {
        return "[]";
      }
    },
    () => "[]",
  );
  return useMemo(() => {
    try {
      const v = JSON.parse(raw);
      return Array.isArray(v) ? (v as number[]) : [];
    } catch {
      return [];   // a corrupt draft is not worth a crash
    }
  }, [raw]);
}

export function SquadBuilder({
  pool,
  fixtures,
  gw,
  meta,
}: {
  pool: Prediction[];
  fixtures: Record<string, TickerFixture[]>;
  gw: number;
  meta: TeamResponse["meta"];
}) {
  const router = useRouter();
  const params = useSearchParams();
  const byId = useMemo(() => new Map(pool.map((p) => [p.element_id, p])), [pool]);

  const saved = useSavedDraft();
  // A shared link wins over a local draft — following someone's squad should show you THEIR
  // squad, not silently reopen your own half-finished one. Both are derived during render,
  // so there is no hydration effect and no flash of an empty squad.
  const linked = useMemo(
    () => decodeSquad(params.get("s")).filter((id) => byId.has(id)),
    [params, byId],
  );
  const initial = linked.length ? linked : saved.filter((id) => byId.has(id));

  // `null` means "untouched, still showing whatever we arrived with".
  const [edited, setEdited] = useState<number[] | null>(null);
  const [viewingOverride, setViewingOverride] = useState<boolean | null>(null);
  const ids = edited ?? initial;
  const viewing = viewingOverride ?? linked.length > 0;

  const setIds = useCallback(
    (next: number[] | ((cur: number[]) => number[])) =>
      setEdited((cur) => (typeof next === "function" ? next(cur ?? initial) : next)),
    [initial],
  );

  // Writing to an external store IS what an effect is for.
  useEffect(() => {
    if (edited === null) return;   // nothing typed yet; don't overwrite a draft with itself
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(edited));
    } catch {
      /* private mode — the draft just doesn't survive a reload */
    }
  }, [edited]);

  const picks = useMemo(
    () => ids.map((id) => byId.get(id)).filter((p): p is Prediction => !!p),
    [ids, byId],
  );
  const cost = totalCost(picks);
  const problems = violations(picks);
  const complete = picks.length === SQUAD_SIZE && problems.length === 0;

  const add = useCallback((p: Prediction) => setIds((cur) => [...cur, p.element_id]), [setIds]);
  const remove = useCallback((id: number) => setIds((cur) => cur.filter((x) => x !== id)), [setIds]);

  const share = () => {
    const url = `${window.location.pathname}?s=${encodeSquad(ids)}`;
    router.replace(url, { scroll: false });
    navigator.clipboard?.writeText(window.location.origin + url).catch(() => {});
  };

  if (viewing && complete) {
    return (
      <div className="flex flex-col gap-3">
        <div className="mx-auto flex w-full max-w-5xl items-center justify-between gap-3 px-4 pt-4">
          <button
            type="button"
            onClick={() => setViewingOverride(false)}
            className="press t-label rounded-full border border-black/10 px-3 py-1.5 text-[11px] text-black/60 hover:border-emerald-600 hover:text-emerald-600 dark:border-white/10 dark:text-white/60"
          >
            ← edit squad
          </button>
          <button
            type="button"
            onClick={share}
            className="press t-label rounded-full bg-emerald-600 px-3 py-1.5 text-[11px] text-white"
          >
            copy share link
          </button>
        </div>
        <TeamDashboard data={buildTeamResponse(picks, gw, meta)} fixtures={fixtures} source="manual" />
      </div>
    );
  }

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-4 px-4 py-6">
      <div>
        <h1 className="t-title text-xl font-bold">Build a squad</h1>
        <p className="mt-0.5 text-sm text-black/50 dark:text-white/50">
          Fifteen players, £{BUDGET.toFixed(0)}m, max 3 per club — the real rules. No account,
          no team id. Works before the season starts, when the FPL API has no squads to fetch.
        </p>
      </div>

      <Summary
        picks={picks}
        cost={cost}
        problems={problems}
        complete={complete}
        onAuto={() => setIds(autoPick(pool).map((p) => p.element_id))}
        onClear={() => setIds([])}
        onView={() => setViewingOverride(true)}
      />

      <SquadSlots picks={picks} onRemove={remove} />

      <Picker pool={pool} picks={picks} onAdd={add} />
    </main>
  );
}

// --- the running verdict --------------------------------------------------------------- //
function Summary({
  picks, cost, problems, complete, onAuto, onClear, onView,
}: {
  picks: Prediction[];
  cost: number;
  problems: { rule: string; detail: string }[];
  complete: boolean;
  onAuto: () => void;
  onClear: () => void;
  onView: () => void;
}) {
  const left = Math.round((BUDGET - cost) * 10) / 10;
  const over = left < 0;
  return (
    <div className="flex flex-col gap-2.5 rounded-2xl border border-black/10 p-3 shadow-sm dark:border-white/10">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex items-end gap-5">
          <Metric label="picked" value={`${picks.length}/${SQUAD_SIZE}`} />
          <Metric
            label={over ? "over budget" : "left in the bank"}
            value={`£${Math.abs(left).toFixed(1)}m`}
            tone={over ? "bad" : undefined}
          />
          <Metric label="squad xP" value={picks.reduce((s, p) => s + p.xp, 0).toFixed(1)} />
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <button type="button" onClick={onAuto} className="press min-h-9 rounded-full border border-black/10 px-3 py-1.5 text-[12px] font-semibold hover:border-emerald-600 hover:text-emerald-600 dark:border-white/10">
            Auto-pick
          </button>
          {picks.length > 0 && (
            <button type="button" onClick={onClear} className="press min-h-9 rounded-full border border-black/10 px-3 py-1.5 text-[12px] font-semibold text-black/55 hover:border-rose-500 hover:text-rose-500 dark:border-white/10 dark:text-white/55">
              Clear
            </button>
          )}
          <button
            type="button"
            onClick={onView}
            disabled={!complete}
            className="press min-h-9 rounded-full bg-emerald-600 px-4 py-1.5 text-[12px] font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            View my team →
          </button>
        </div>
      </div>

      {/* Budget as a bar: the number tells you how much, the bar tells you how close. */}
      <div className="h-1.5 overflow-hidden rounded-full bg-black/[.07] dark:bg-white/[.10]">
        <div
          className="h-full rounded-full transition-[width] duration-200"
          style={{
            width: `${Math.min(100, (cost / BUDGET) * 100)}%`,
            background: over ? "var(--rose)" : "#059669",
          }}
        />
      </div>

      {problems.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {problems.map((v, i) => (
            <span key={i} className="rounded-full border border-[var(--amber-br)] bg-[var(--amber-bg)] px-2.5 py-1 text-[11px] font-semibold text-[var(--amber-fg)]">
              {v.rule}: {v.detail}
            </span>
          ))}
        </div>
      )}
      {picks.length === SQUAD_SIZE && problems.length === 0 && (
        <p className="text-[11px] text-emerald-700 dark:text-emerald-400">
          Legal squad — 2/5/5/3, under budget, no club over three.
        </p>
      )}
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: "bad" }) {
  return (
    <div className="flex flex-col">
      <span className={`t-title text-xl font-bold tabular-nums ${tone === "bad" ? "text-[var(--rose)]" : ""}`}>
        {value}
      </span>
      <span className="text-[11px] text-black/50 dark:text-white/50">{label}</span>
    </div>
  );
}

// --- what you have, and what you still need --------------------------------------------- //
function SquadSlots({ picks, onRemove }: { picks: Prediction[]; onRemove: (id: number) => void }) {
  return (
    <div className="flex flex-col gap-2">
      {POS_ORDER.map((pos) => {
        const mine = picks.filter((p) => p.position === pos).sort((a, b) => b.xp - a.xp);
        const empty = SQUAD_QUOTA[pos] - mine.length;
        return (
          <div key={pos} className="flex items-start gap-2">
            <span className="t-label w-9 flex-none pt-2 text-[10px] text-black/40 dark:text-white/40">
              {pos}
            </span>
            <div className="flex flex-1 flex-wrap gap-1.5">
              {mine.map((p) => {
                const club = getClub(p.team);
                return (
                  <button
                    key={p.element_id}
                    type="button"
                    onClick={() => onRemove(p.element_id)}
                    title={`Remove ${p.web_name}`}
                    className="press group flex min-h-9 items-center gap-1.5 rounded-full border border-black/10 py-1 pl-1 pr-2.5 hover:border-rose-500 dark:border-white/10"
                  >
                    <Jersey primary={club.primary} secondary={club.secondary} pattern={club.pattern} width={18} height={17} className="block flex-none" />
                    <span className="text-[12px] font-semibold">{p.web_name}</span>
                    <span className="tabular-nums text-[11px] text-black/45 dark:text-white/45">£{p.price.toFixed(1)}</span>
                    <span aria-hidden className="text-[11px] text-black/30 group-hover:text-rose-500 dark:text-white/30">✕</span>
                  </button>
                );
              })}
              {Array.from({ length: Math.max(0, empty) }, (_, i) => (
                <span
                  key={`e${i}`}
                  className="flex min-h-9 min-w-[84px] items-center justify-center rounded-full border border-dashed border-black/15 px-3 text-[11px] text-black/30 dark:border-white/15 dark:text-white/30"
                >
                  empty
                </span>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// --- the picker -------------------------------------------------------------------------- //
function Picker({ pool, picks, onAdd }: { pool: Prediction[]; picks: Prediction[]; onAdd: (p: Prediction) => void }) {
  const counts = countByPos(picks as never);
  // Default to whatever still has a gap, so the next tap is usually the right one already.
  const firstGap = POS_ORDER.find((p) => counts[p] < SQUAD_QUOTA[p]) ?? "ALL";
  const [pos, setPos] = useState<Pos | "ALL">(firstGap);
  const [q, setQ] = useState("");
  const [touched, setTouched] = useState(false);
  const active = touched ? pos : firstGap;

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return pool
      .filter(
        (p) =>
          (active === "ALL" || p.position === active) &&
          (needle === "" ||
            p.web_name.toLowerCase().includes(needle) ||
            (p.team ?? "").toLowerCase().includes(needle)),
      )
      .sort((a, b) => b.xp - a.xp)
      .slice(0, 60);
  }, [pool, active, q]);

  const chosen = new Set(picks.map((p) => p.element_id));

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-col gap-2 rounded-2xl border border-black/10 p-2.5 shadow-sm dark:border-white/10">
        <div className="flex flex-wrap items-center gap-1.5">
          {(["ALL", ...POS_ORDER] as const).map((p) => {
            const on = active === p;
            const full = p !== "ALL" && counts[p] >= SQUAD_QUOTA[p];
            return (
              <button
                key={p}
                onClick={() => { setTouched(true); setPos(p); }}
                aria-pressed={on}
                className={`press min-h-8 flex-none rounded-full border px-3 py-1.5 text-[11px] font-semibold ${
                  on ? "border-emerald-600 bg-emerald-600 text-white"
                     : "border-black/10 text-black/55 dark:border-white/10 dark:text-white/55"
                }`}
              >
                {p}
                {p !== "ALL" && (
                  <span className={on ? "opacity-80" : full ? "text-emerald-600" : "opacity-50"}>
                    {" "}{counts[p]}/{SQUAD_QUOTA[p]}
                  </span>
                )}
              </button>
            );
          })}
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search player or club…"
            aria-label="Search player or club"
            className="min-h-9 min-w-[150px] flex-1 rounded-full border border-black/15 bg-transparent px-3 py-1.5 text-sm outline-none ring-[var(--focus)] focus:ring-2 dark:border-white/15"
          />
        </div>
      </div>

      <ul className="overflow-hidden rounded-2xl border border-black/10 shadow-sm dark:border-white/10">
        {rows.length === 0 && (
          <li className="px-3 py-4 text-[13px] text-black/50 dark:text-white/50">No players match that.</li>
        )}
        {rows.map((p) => {
          const club = getClub(p.team);
          const picked = chosen.has(p.element_id);
          const reason = picked ? null : blockedReason(p, picks);
          const disabled = picked || reason !== null;
          return (
            <li key={p.element_id}>
              <button
                type="button"
                onClick={() => !disabled && onAdd(p)}
                disabled={disabled}
                className={`press flex min-h-12 w-full items-center gap-2 border-b border-black/[.06] px-2.5 py-1.5 text-left dark:border-white/[.06] ${
                  disabled ? "cursor-not-allowed opacity-45" : "hover:bg-black/[.02] dark:hover:bg-white/[.03]"
                }`}
              >
                <Jersey primary={club.primary} secondary={club.secondary} pattern={club.pattern} width={22} height={21} className="block flex-none" />
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="flex min-w-0 items-center gap-1">
                    <span className="truncate text-[13px] font-semibold">{p.web_name}</span>
                    <span className="flex-none font-mono text-[10px] text-black/35 dark:text-white/35">{club.shortCode}</span>
                  </span>
                  <span className="text-[10px] tabular-nums text-black/45 dark:text-white/45">
                    {p.position} · {p.ownership.toFixed(1)}% owned
                    {reason ? <span className="text-[var(--amber-fg)]"> · {reason}</span> : null}
                  </span>
                </span>
                <span className="w-12 flex-none text-right tabular-nums text-[13px] text-black/60 dark:text-white/60">
                  £{p.price.toFixed(1)}
                </span>
                <span className="w-10 flex-none text-right t-title text-[15px] font-bold tabular-nums text-emerald-600">
                  {p.xp.toFixed(1)}
                </span>
                <span aria-hidden className="w-4 flex-none text-center text-[15px] text-black/25 dark:text-white/25">
                  {picked ? "✓" : disabled ? "" : "+"}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      <p className="text-[11px] text-black/40 dark:text-white/40">
        Top 60 by xP for this filter. Auto-pick takes players in xP order while the cheapest
        possible filling of every remaining slot still fits the budget — a legal starting point
        to edit, not an optimal squad.
      </p>
    </div>
  );
}
