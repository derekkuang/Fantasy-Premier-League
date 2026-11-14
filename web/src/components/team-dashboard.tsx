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
import { Card, Flag, Stat } from "@/components/ui";
import { SquadBoard } from "@/components/pitch";
import { CaptainCompare } from "@/components/captain-compare";
import { PlayerSheet, type SwapOption } from "@/components/player-sheet";
import { Explained } from "@/components/explained";
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
      <header className="flex flex-col gap-1">
        {/* One way back. A built squad has its own "Edit squad" bar above this. */}
        {!manual && (
          <Link href="/squad" className="press w-fit text-[13px] text-[var(--emerald-text)] hover:underline">
            ← Another team
          </Link>
        )}
        <h1 className="t-title text-[22px] font-bold">
          {manual ? `Your squad · GW${data.gw}` : `Team ${data.entry_id} · GW${data.gw}`}
        </h1>
      </header>

      {!manual && data.picks_gw != null && data.picks_gw < data.gw && (
        // Honest join: FPL reveals a gameweek's picks only after its deadline, so mid-week
        // the squad shown is the manager's current one from the previous gameweek, priced
        // against the upcoming projections. Transfers made for GW{gw} appear once its
        // deadline passes — FPL doesn't expose them earlier.
        <p className="text-[13px] leading-relaxed text-muted">
          Your squad as of GW{data.picks_gw}, projected for GW{data.gw}. Transfers for GW{data.gw}
          appear after its deadline, when FPL reveals them.
        </p>
      )}

      <Card className="p-5">
        <div className="flex items-end justify-between gap-4">
          <Stat
            label="projected points, best XI"
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

      <div className="grid gap-5 lg:grid-cols-[minmax(0,430px)_minmax(0,1fr)] lg:items-start">
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

        <div className="flex min-w-0 flex-col gap-5">
          <CaptainCompare starters={starters} basis={basis} onBasis={setBasis} captainId={captainId} />
          {!manual && <TransferCard move={data.best_transfer} freeTransfers={data.free_transfers} />}
          <BalanceCard flags={health.flags} />
          {data.unscored_elements.length > 0 && (
            <p className="text-[13px] text-muted">
              {data.unscored_elements.length} of your players have no projection yet and are left
              out of the total.
            </p>
          )}
          {/* Shows nothing at all while the advisor is switched off. */}
          <AdvisorChat
            gw={data.gw}
            owned={data.squad.map((p) => p.element_id)}
            bank={data.bank}
            freeTransfers={data.free_transfers}
          />
        </div>
      </div>

      {open && (
        <PlayerSheet
          player={open}
          gw={data.gw}
          role={open.is_captain || open.element_id === captainId ? "captain" : openIsStarter ? "starter" : "bench"}
          swap={{ title: openIsStarter ? "Swap with the bench" : "Bring into the XI", options: swapOptions }}
          onClose={() => setOpenId(null)}
        />
      )}
    </main>
  );
}

function TransferCard({ move, freeTransfers }: { move: TransferMove | null; freeTransfers: number }) {
  return (
    <section className="flex flex-col gap-2">
      <Explained label="How is this chosen?" head={<h2 className="text-[13px] font-semibold text-muted">Best transfer</h2>}>
        Judged on your whole squad at its best possible XI, so swapping bench and starters
        doesn&apos;t change it.{freeTransfers < 1 ? " With no free transfer it has to beat the 4-point hit." : ""}
      </Explained>
      <Card className="px-4 py-3">
        {move && move.net_gain > 0 ? (
          <p className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-[14px]">
            <span>
              <span className="text-muted">Out</span> <strong>{move.out.web_name}</strong>{" "}
              <span className="text-muted">→ in</span> <strong>{move.in.web_name}</strong>
            </span>
            <span className="tabular-nums" style={{ color: "var(--emerald-text)" }}>
              +{move.net_gain.toFixed(1)} xP{freeTransfers < 1 ? " after the hit" : ""}
            </span>
          </p>
        ) : (
          <p className="text-[14px] text-muted">No transfer beats holding this week.</p>
        )}
      </Card>
    </section>
  );
}

function BalanceCard({ flags }: { flags: BalanceFlag[] }) {
  // One at a time. Opening a second flag closes the first, so the column keeps its shape
  // and the detail you are reading is always the detail you just asked for — with several
  // expanded at once the card grows past the fold and the verdicts stop being scannable.
  const [openIdx, setOpenIdx] = useState<number | null>(null);

  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-[13px] font-semibold text-muted">Squad health</h2>
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
    </section>
  );
}
