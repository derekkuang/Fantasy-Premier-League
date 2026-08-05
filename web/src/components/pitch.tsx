"use client";
// The pitch / formation view — a CONTROLLED component: the XI (starterIds), captain, and
// open-player state live in TeamDashboard so projected points, formation, and the captain
// table all react together. Here we just render starters in positional rows + the bench,
// and call onOpen when a token is tapped.

import { fdrFor, type SquadPlayer, type TickerFixture } from "@/lib/api";
import { fdrColour, fdrGlyph, getClub } from "@/lib/clubs";
import { formationLabel, POS_ORDER } from "@/lib/formation";
import { Jersey, JerseyDefs } from "@/components/jersey";

type FixtureMap = Record<string, TickerFixture[]>;
type Pip = { oppCode: string; venue: "H" | "A"; fdr: number };

function pipFor(player: SquadPlayer, fixtures: FixtureMap): Pip | null {
  const fx = fixtures[player.team ?? ""]?.[0];
  if (!fx) return null;
  return { oppCode: getClub(fx.opp).shortCode, venue: fx.home ? "H" : "A", fdr: fdrFor(player.position, fx) };
}

export function SquadBoard({
  squad,
  fixtures,
  starterIds,
  captainId,
  isModified,
  lastSwap,
  onOpen,
  onReset,
}: {
  squad: SquadPlayer[];
  fixtures: FixtureMap;
  starterIds: Set<number>;
  captainId: number | null;
  isModified: boolean;
  lastSwap: string | null;
  onOpen: (id: number) => void;
  onReset: () => void;
}) {
  const starters = squad.filter((p) => starterIds.has(p.element_id));
  const bench = squad.filter((p) => !starterIds.has(p.element_id));
  const rows = POS_ORDER.map((pos) => ({
    pos,
    players: starters.filter((p) => p.position === pos).sort((a, b) => b.xp - a.xp),
  })).filter((r) => r.players.length > 0);

  return (
    <section className="flex flex-col gap-2">
      <JerseyDefs />
      <div className="flex items-center justify-between px-0.5">
        <h2 className="t-label text-[11px] text-black/40 dark:text-white/40">
          Your squad · tap a player
        </h2>
        <div className="flex items-center gap-1.5">
          <span className="rounded-full bg-emerald-600 px-2.5 py-1 text-[11px] font-bold tabular-nums text-white">
            {formationLabel(starters)}
          </span>
          {isModified && (
            <button
              type="button"
              onClick={onReset}
              className="press min-h-8 rounded-full border border-black/10 px-3 py-1.5 text-[11px] font-semibold text-black/55 hover:border-emerald-600 hover:text-emerald-600 dark:border-white/10 dark:text-white/55"
            >
              Auto-pick
            </button>
          )}
        </div>
      </div>

      {lastSwap && (
        <div className="flex items-center gap-1.5 rounded-[10px] border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1.5 text-[11px] text-emerald-700 dark:text-emerald-300">
          <span>✓</span>
          <span>{lastSwap}</span>
        </div>
      )}

      {/* Pitch */}
      <div className="relative overflow-hidden rounded-2xl border border-black/10 shadow-sm dark:border-white/10 bg-gradient-to-b from-teal-700 to-teal-800 dark:from-[#0b3d38] dark:to-[#072a27]">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 [background:repeating-linear-gradient(180deg,rgba(255,255,255,.055)_0_44px,transparent_44px_88px)] dark:[background:repeating-linear-gradient(180deg,rgba(255,255,255,.035)_0_44px,transparent_44px_88px)]"
        />
        <div aria-hidden className="pointer-events-none absolute left-0 right-0 top-1/2 h-px bg-white/25" />
        <div aria-hidden className="pointer-events-none absolute left-1/2 top-1/2 h-24 w-24 -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/25" />
        <div aria-hidden className="pointer-events-none absolute left-1/2 top-0 h-[76px] w-[172px] -translate-x-1/2 rounded-b-[3px] border border-t-0 border-white/25" />
        <div aria-hidden className="pointer-events-none absolute bottom-0 left-1/2 h-[76px] w-[172px] -translate-x-1/2 rounded-t-[3px] border border-b-0 border-white/25" />

        <ol className="relative flex min-h-[452px] flex-col justify-between gap-2.5 px-2 pb-[18px] pt-4">
          {rows.map((row) => (
            <li key={row.pos} className="flex items-start justify-center gap-0.5">
              {row.players.map((p) => (
                <PlayerToken
                  key={p.element_id}
                  player={p}
                  pip={pipFor(p, fixtures)}
                  isCaptain={p.element_id === captainId}
                  onOpen={() => onOpen(p.element_id)}
                />
              ))}
            </li>
          ))}
        </ol>
      </div>

      <BenchStrip bench={bench} fixtures={fixtures} onOpen={onOpen} />
    </section>
  );
}

function PlayerToken({ player, pip, isCaptain, onOpen }: { player: SquadPlayer; pip: Pip | null; isCaptain: boolean; onOpen: () => void }) {
  const club = getClub(player.team);
  return (
    <button
      type="button"
      onClick={onOpen}
      title={`${player.web_name} — tap for detail`}
      className="press relative flex w-[74px] flex-col items-center gap-1 rounded-[10px] pt-0.5 text-inherit hover:bg-white/[.09] focus-visible:ring-2 focus-visible:ring-white/60"
    >
      <div className="relative h-11 w-[46px]">
        <Jersey
          primary={club.primary}
          secondary={club.secondary}
          pattern={club.pattern}
          width={46}
          height={44}
          className="block [filter:drop-shadow(0_2px_3px_rgba(0,0,0,.3))]"
        />
        <span
          className="absolute -left-1 -top-[3px] rounded border border-black/25 px-[3px] font-mono text-[10px] font-bold"
          style={{ background: club.primary, color: club.text }}
        >
          {club.shortCode}
        </span>
        {isCaptain && (
          <span
            title="Captain"
            className="absolute -right-1 -top-[3px] grid h-4 w-4 place-items-center rounded-full border-[1.5px] border-white/85 bg-emerald-600 text-[9px] font-bold text-white"
          >
            C
          </span>
        )}
      </div>
      <span className="max-w-[72px] truncate rounded-full bg-black/60 px-[7px] py-0.5 text-[11px] font-semibold text-white">
        {player.web_name}
      </span>
      <div className="flex items-center gap-[3px]">
        <span className="rounded bg-white/15 px-1 text-[10px] tabular-nums text-white/80">£{player.price.toFixed(1)}</span>
        <span className="rounded bg-emerald-50 px-[5px] text-[11px] font-bold tabular-nums text-emerald-800">
          {player.xp.toFixed(1)}
        </span>
      </div>
      {pip && <FixturePip pip={pip} />}
    </button>
  );
}

function FixturePip({ pip }: { pip: Pip }) {
  return (
    <div className="flex items-center gap-[3px] pb-0.5 leading-none">
      <span className="font-mono text-[10px] font-semibold text-white/70">
        {pip.oppCode} ({pip.venue})
      </span>
      <span
        className="grid h-[14px] min-w-[14px] place-items-center rounded-[3.5px] text-[10px] font-bold leading-none tabular-nums"
        style={{ background: fdrColour(pip.fdr), color: fdrGlyph(pip.fdr) }}
      >
        {pip.fdr}
      </span>
    </div>
  );
}

function BenchStrip({ bench, fixtures, onOpen }: { bench: SquadPlayer[]; fixtures: FixtureMap; onOpen: (id: number) => void }) {
  const benchXp = bench.reduce((s, p) => s + p.xp, 0);
  const benchSpend = bench.reduce((s, p) => s + p.price, 0);
  const ordered = [...bench].sort(
    (a, b) => POS_ORDER.indexOf(a.position) - POS_ORDER.indexOf(b.position) || b.xp - a.xp,
  );
  return (
    <div className="rounded-2xl border border-black/10 bg-white/70 p-3 shadow-sm dark:border-white/10 dark:bg-white/5">
      <div className="mb-2 flex items-baseline justify-between">
        <span className="t-label text-[11px] text-black/40 dark:text-white/40">Bench</span>
        <span className="text-[11px] tabular-nums text-black/40 dark:text-white/40">
          £{benchSpend.toFixed(1)}m · {benchXp.toFixed(1)} xP
        </span>
      </div>
      <div className="grid grid-cols-4 gap-1.5">
        {ordered.map((p, i) => {
          const club = getClub(p.team);
          const pip = pipFor(p, fixtures);
          return (
            <button
              type="button"
              key={p.element_id}
              onClick={() => onOpen(p.element_id)}
              className="press flex min-h-11 flex-col items-center gap-0.5 rounded-[10px] border border-black/[.06] px-0.5 py-1.5 text-inherit opacity-90 hover:border-emerald-500 hover:opacity-100 dark:border-white/[.06]"
            >
              <div className="flex items-center gap-[3px]">
                <span className="text-[10px] tabular-nums text-black/40 dark:text-white/40">{i + 1}</span>
                <Jersey primary={club.primary} secondary={club.secondary} pattern={club.pattern} width={26} height={25} className="block" />
              </div>
              <span className="max-w-[90%] truncate text-[11px] font-semibold">{p.web_name}</span>
              <div className="flex items-center gap-[3px]">
                <span className="text-[10px] tabular-nums text-black/40 dark:text-white/40">{p.position}</span>
                <span className="text-[10px] tabular-nums text-black/55 dark:text-white/55">£{p.price.toFixed(1)}</span>
                <span className="text-[10px] font-bold tabular-nums text-emerald-600">{p.xp.toFixed(1)}</span>
              </div>
              {pip && (
                <div className="flex items-center gap-[3px]">
                  <span className="font-mono text-[10px] text-black/40 dark:text-white/40">
                    {pip.oppCode} ({pip.venue})
                  </span>
                  <span
                    className="grid h-[14px] min-w-[14px] place-items-center rounded-[3.5px] text-[10px] font-bold leading-none tabular-nums"
                    style={{ background: fdrColour(pip.fdr), color: fdrGlyph(pip.fdr) }}
                  >
                    {pip.fdr}
                  </span>
                </div>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
