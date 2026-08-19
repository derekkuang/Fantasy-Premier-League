"use client";
// Orchestrates the interactive dashboard. Owns the live XI (starterIds), the captain basis,
// and the open-player sheet — so projected points, formation, captain, and swap deltas all
// recompute together. Responsive: single column on mobile, pitch | cards on desktop.

import Link from "next/link";
import { useMemo, useState } from "react";
import type { TeamResponse, TickerFixture, TransferMove } from "@/lib/api";
import {
  chooseCaptainId,
  countByPos,
  projectedPoints,
  swapLegal,
} from "@/lib/formation";
import { computeHealth, type BalanceFlag } from "@/lib/balance";
import { Card, Flag, SectionTitle, Stat } from "@/components/ui";
import { SquadBoard } from "@/components/pitch";
import { CaptainCompare } from "@/components/captain-compare";
import { PlayerSheet, type SwapOption } from "@/components/player-sheet";
import { AdvisorChat } from "@/components/advisor-chat";

export function TeamDashboard({
  data,
  fixtures,
  source = "fpl",
}: {
  data: TeamResponse;
  fixtures: Record<string, TickerFixture[]>;
  /** "manual" = assembled in the builder rather than fetched from an entry id. The squad
   *  maths is identical either way; what differs is that a hand-built squad has no prior
   *  squad to transfer FROM, so the transfer card would be answering a question nobody
   *  asked. Hiding it beats showing "no transfer beats holding" about a squad with no
   *  holdings. */
  source?: "fpl" | "manual";
}) {
  const manual = source === "manual";
  const originalIds = useMemo(
    () => new Set(data.squad.filter((p) => p.is_starter).map((p) => p.element_id)),
    [data],
  );
  const [starterIds, setStarterIds] = useState<Set<number>>(() => new Set(originalIds));
  const [basis, setBasis] = useState<"rank" | "xp">("xp");
  const [openId, setOpenId] = useState<number | null>(null);
  const [lastSwap, setLastSwap] = useState<string | null>(null);

  // The backend sends the authoritative baseline (data.projected_points / captain / balance)
  // for the RECOMMENDED XI — that's the API contract for non-UI consumers. Here we recompute
  // client-side because the XI is user-editable (swaps) and must update instantly without a
  // server round-trip. At the initial (unmodified) XI these match the backend by construction
  // (default basis "xp" -> best_xi captain; computeHealth mirrors check_balance, parity-tested).
  const nameOf = (id: number) => data.squad.find((p) => p.element_id === id)?.web_name ?? "?";
  const starters = data.squad.filter((p) => starterIds.has(p.element_id));
  const captainId = chooseCaptainId(starters, basis);
  const projected = projectedPoints(starters, captainId);
  const health = computeHealth(data.squad, starterIds); // live: recomputes as the XI changes
  const isModified =
    starterIds.size !== originalIds.size || [...starterIds].some((id) => !originalIds.has(id));

  function applySwap(outId: number, inId: number) {
    const next = new Set(starterIds);
    next.delete(outId);
    next.add(inId);
    setStarterIds(next);
    setLastSwap(`swapped ${nameOf(outId)} ↔ ${nameOf(inId)}`);
    setOpenId(null);
  }

  function resetXI() {
    setStarterIds(new Set(originalIds));
    setLastSwap(null);
  }

  // Legal swap options for the open player, each with the projected-points delta.
  const open = openId != null ? data.squad.find((p) => p.element_id === openId) ?? null : null;
  const openIsStarter = open ? starterIds.has(open.element_id) : false;
  const swapOptions: SwapOption[] = useMemo(() => {
    if (!open) return [];
    const counts = countByPos(starters);
    const base = projected;
    const evalSwap = (outId: number, inId: number) => {
      const set = new Set(starterIds);
      set.delete(outId);
      set.add(inId);
      const s = data.squad.filter((p) => set.has(p.element_id));
      return projectedPoints(s, chooseCaptainId(s, basis)) - base;
    };
    const opts: SwapOption[] = openIsStarter
      ? data.squad
          .filter((b) => !starterIds.has(b.element_id) && swapLegal(counts, open.position, b.position))
          .map((b) => ({ other: b, delta: evalSwap(open.element_id, b.element_id), apply: () => applySwap(open.element_id, b.element_id) }))
      : starters
          .filter((s) => swapLegal(counts, s.position, open.position))
          .map((s) => ({ other: s, delta: evalSwap(s.element_id, open.element_id), apply: () => applySwap(s.element_id, open.element_id) }));
    return opts.sort((a, b) => b.delta - a.delta);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, starterIds, basis]);

  return (
    <main
      // `enter` bridges the swap from the pulsing skeleton in loading.tsx — without it
      // the page snaps from placeholder to content in a single frame
      className="enter mx-auto flex w-full max-w-5xl flex-col gap-5 px-4 py-6"
    >
      <header className="flex items-end justify-between gap-3">
        <div className="flex flex-col gap-0.5">
          <Link href="/" className="press text-[13px] text-emerald-600 hover:underline">
            ← another team
          </Link>
          <h1 className="t-title text-lg font-semibold">
            {manual ? `Your squad · GW${data.gw}` : `Team ${data.entry_id} · GW${data.gw}`}
          </h1>
        </div>
        <span className="rounded-full bg-black/5 px-2 py-1 font-mono text-[11px] text-black/50 dark:bg-white/10 dark:text-white/50">
          {data.meta.model_ver}
        </span>
      </header>

      <Card className="p-5">
        <div className="flex items-end justify-between gap-4">
          <Stat
            label="projected points (best XI, C doubled)"
            value={starters.length ? projected.toFixed(1) : "—"}
          />
          <div className="flex gap-6 text-right">
            <Stat label="bank" value={`£${data.bank.toFixed(1)}`} />
            {manual ? (
              <Stat label="squad cost" value={`£${(100 - data.bank).toFixed(1)}`} />
            ) : (
              <Stat label={data.free_transfers === 1 ? "free transfer" : "free transfers"} value={data.free_transfers} />
            )}
          </div>
        </div>
      </Card>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,430px)_1fr] lg:items-start">
        <SquadBoard
          squad={data.squad}
          fixtures={fixtures}
          starterIds={starterIds}
          captainId={captainId}
          isModified={isModified}
          lastSwap={lastSwap}
          onOpen={setOpenId}
          onReset={resetXI}
        />

        <div className="flex flex-col gap-5">
          <CaptainCompare starters={starters} basis={basis} onBasis={setBasis} captainId={captainId} />
          {!manual && <TransferCard move={data.best_transfer} freeTransfers={data.free_transfers} />}
          {/* Sits BELOW the free precomputed answer on purpose — the chip prompts are all
              follow-ups to it, which is the only thing it is worth paying a model for. */}
          <AdvisorChat
            gw={data.gw}
            owned={data.squad.map((p) => p.element_id)}
            bank={data.bank}
            freeTransfers={data.free_transfers}
          />
          {data.unscored_elements.length > 0 && (
            <p className="px-1 text-xs text-black/50 dark:text-white/50">
              {data.unscored_elements.length} owned player(s) have no prediction (promoted or
              low-data team) and are excluded from the projection.
            </p>
          )}
          <BalanceCard flags={health.flags} />
        </div>
      </div>

      <p className="px-1 text-center text-[11px] leading-relaxed text-black/40 dark:text-white/40">
        Club colours only — generic kit shapes, no official kits or crests. Not affiliated with
        the Premier League. xP is model-estimated; how well it does is measured and published.
      </p>

      {open && (
        <PlayerSheet
          player={open}
          fixtures={fixtures[open.team ?? ""] ?? []}
          swapTitle={openIsStarter ? "Bench — swap out for" : "Start — swap in for"}
          swapOptions={swapOptions}
          onClose={() => setOpenId(null)}
        />
      )}
    </main>
  );
}

function TransferCard({ move, freeTransfers }: { move: TransferMove | null; freeTransfers: number }) {
  return (
    <div className="flex flex-col gap-1">
      <SectionTitle>Best transfer</SectionTitle>
      <Card className="p-4">
        {move && move.net_gain > 0 ? (
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-rose-600 dark:text-rose-400">OUT {move.out.web_name}</span>
              <span className="text-black/40 dark:text-white/40">→</span>
              <span className="text-emerald-600 dark:text-emerald-400">IN {move.in.web_name}</span>
            </div>
            <div className="flex items-center justify-between text-xs text-black/55 dark:text-white/55">
              <span className="tabular-nums">cost £{move.cost.toFixed(1)}m</span>
              <span className="tabular-nums">
                +{move.xp_gain.toFixed(2)} xP → net {move.net_gain > 0 ? "+" : ""}
                {move.net_gain.toFixed(2)}
                {freeTransfers < 1 ? " (after −4)" : ""}
              </span>
            </div>
          </div>
        ) : (
          <p className="text-sm text-black/55 dark:text-white/55">
            No transfer beats holding this week — your squad is already well-placed.
          </p>
        )}
      </Card>
      <p className="px-1 text-[10px] text-black/40 dark:text-white/40">
        For your 15 as a whole, judged at your best possible XI — so it doesn&apos;t change when
        you swap bench and starters.
      </p>
    </div>
  );
}

function BalanceCard({ flags }: { flags: BalanceFlag[] }) {
  // One at a time. Opening a second flag closes the first, so the column keeps its shape
  // and the detail you are reading is always the detail you just asked for — with several
  // expanded at once the card grows past the fold and the verdicts stop being scannable.
  const [openIdx, setOpenIdx] = useState<number | null>(null);

  return (
    <div>
      <SectionTitle>Squad health · tap a flag</SectionTitle>
      <div className="flex flex-col gap-2">
        {flags.map((f, i) => (
          <Flag
            key={i}
            level={f.level}
            detail={f.detail}
            open={openIdx === i}
            onToggle={() => setOpenIdx((cur) => (cur === i ? null : i))}
          >
            {f.message}
          </Flag>
        ))}
      </div>
    </div>
  );
}
