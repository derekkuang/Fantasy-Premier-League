"use client";
// True-FDR fixture ticker: teams down, gameweeks across.
//
// The lens decides both what each cell shows and how the rows are ranked. "Overall" shows
// both tracks — attack (chance to score) and defence (chance of a clean sheet) — ranked by
// their combined difficulty, because the two runs disagree far too often to collapse into
// one. Picking Attack or Defence narrows every cell to that single track and ranks by it.
//
// The grid is its own two-axis scroll region so the page never scrolls sideways, and both
// sticky axes have a scroll range to pin against.

import { useMemo, useState } from "react";
import type { FixturesResponse, TickerFixture } from "@/lib/api";
import { fdrColour, fdrGlyph, getClub } from "@/lib/clubs";
import { Jersey } from "@/components/jersey";
import { SplitCell, type TickerLens } from "@/components/split-cell";

type Win = 3 | 5 | 8;

// Cell width scales with the window so a short window doesn't leave dead space. These must
// be literal class strings — Tailwind scans source text, so a template-built class never
// generates any CSS.
const CELL_W: Record<Win, string> = {
  3: "w-[116px] min-w-[116px] lg:w-[168px] lg:min-w-[168px]",
  5: "w-[104px] min-w-[104px] lg:w-[132px] lg:min-w-[132px]",
  8: "w-[96px] min-w-[96px] lg:w-[112px] lg:min-w-[112px]",
};
const TEAM_W = "w-[132px] min-w-[132px] lg:w-[150px] lg:min-w-[150px]";

const PILL = "cursor-pointer rounded-full border px-[11px] py-[5px] text-xs font-semibold";
const PILL_ON = "border-emerald-600 bg-emerald-600 text-white";
const PILL_OFF = "border-black/10 text-black/55 dark:border-white/10 dark:text-white/55";
const GROUP_LABEL = "text-[10px] font-semibold uppercase tracking-[.07em] text-black/40 dark:text-white/40";

const LENS_HINT: Record<TickerLens, string> = {
  overall: "left half attack · right half defence — ranked by combined difficulty",
  attack: "attack only — ranked by the easiest run of fixtures to score in",
  defence: "defence only — ranked by the easiest run of fixtures to keep a clean sheet in",
};

// --- legend ------------------------------------------------------------------------ //
function FdrLegend({ lens }: { lens: TickerLens }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2.5 rounded-2xl border border-black/10 px-3 py-2.5 shadow-sm dark:border-white/10">
      <div className="flex items-center gap-1.5">
        <span className={GROUP_LABEL}>easy</span>
        {[1, 2, 3, 4, 5].map((n) => (
          <span
            key={n}
            title={n === 1 ? "1 — easiest" : n === 5 ? "5 — hardest" : String(n)}
            className="grid h-5 w-5 place-items-center rounded-[5px] text-[11px] font-bold tabular-nums"
            style={{ background: fdrColour(n), color: fdrGlyph(n) }}
          >
            {n}
          </span>
        ))}
        <span className={GROUP_LABEL}>hard</span>
      </div>

      <div className="flex flex-col gap-1">
        {[
          ["A", "attack", "chance to score"],
          ["D", "defence", "chance of a clean sheet"],
        ].map(([letter, term, gloss]) => (
          <span key={letter} className="flex items-center gap-1.5 text-[11px] text-black/55 dark:text-white/55">
            <span className="grid h-4 w-4 place-items-center rounded bg-black/5 text-[9px] font-bold dark:bg-white/10">
              {letter}
            </span>
            <span>
              <strong className="font-semibold text-[var(--foreground)]">{term}</strong> — {gloss}
            </span>
          </span>
        ))}
      </div>

      <span className="text-[11px] text-black/35 dark:text-white/35">{LENS_HINT[lens]}</span>
    </div>
  );
}

// --- controls ---------------------------------------------------------------------- //
function TickerControls({
  win,
  setWin,
  lens,
  setLens,
}: {
  win: Win;
  setWin: (w: Win) => void;
  lens: TickerLens;
  setLens: (l: TickerLens) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-3.5 gap-y-2">
      <span className={GROUP_LABEL}>window</span>
      <div className="flex gap-1.5">
        {([3, 5, 8] as const).map((w) => (
          <button key={w} onClick={() => setWin(w)} className={`${PILL} ${win === w ? PILL_ON : PILL_OFF}`}>
            {w === 8 ? "Full 8" : `Next ${w}`}
          </button>
        ))}
      </div>

      <span className={GROUP_LABEL}>show</span>
      <div className="flex gap-1.5">
        {(["attack", "defence", "overall"] as const).map((l) => (
          <button
            key={l}
            onClick={() => setLens(l)}
            title={LENS_HINT[l]}
            className={`${PILL} ${lens === l ? PILL_ON : PILL_OFF}`}
          >
            {l === "attack" ? "Attack" : l === "defence" ? "Defence" : "Overall"}
          </button>
        ))}
      </div>
    </div>
  );
}

// --- one gameweek cell for one team -------------------------------------------------- //
function FixtureCell({
  fixtures,
  gw,
  teamName,
  lastServed,
  horizon,
  lens,
  cellW,
}: {
  fixtures: TickerFixture[];
  gw: number;
  teamName: string;
  lastServed: number;
  horizon: number;
  lens: TickerLens;
  cellW: string;
}) {
  const cls = `${cellW} border-t border-black/[.06] p-[3px] align-top dark:border-white/[.06]`;

  if (!fixtures.length && gw <= lastServed) {
    // A genuine blank gameweek — real, and worth distinguishing from missing data.
    return (
      <td className={cls}>
        <span
          title={`GW${gw} — blank gameweek for ${teamName}`}
          className="flex h-11 items-center justify-center rounded-lg border border-dashed border-black/[.06] text-[13px] text-black/20 dark:border-white/[.06] dark:text-white/20"
        >
          —
        </span>
      </td>
    );
  }

  if (!fixtures.length) {
    // Beyond what this payload carries — degrade honestly rather than showing a blank.
    return (
      <td className={cls}>
        <span
          title={`GW${gw} — not in this payload (precompute horizon is ${horizon}; the pipeline default is 8)`}
          className="flex h-11 flex-col items-center justify-center rounded-lg border border-dashed border-black/10 text-black/35 dark:border-white/10 dark:text-white/35"
        >
          <span className="text-[9px] font-semibold">pending</span>
          <span className="text-[8px] text-black/20 dark:text-white/20">horizon {horizon}</span>
        </span>
      </td>
    );
  }

  return (
    <td className={cls}>
      <span className="flex flex-col gap-0.5">
        {/* a double gameweek stacks two tiles in the one column */}
        {fixtures.map((f) => {
          const opp = getClub(f.opp);
          return (
            <span
              key={`${f.opp}-${f.home}`}
              title={`GW${f.gw} vs ${f.opp} (${f.home ? "H" : "A"}) — att ${f.attack_fdr} / def ${f.defence_fdr} · λ ${f.lam_for.toFixed(1)} / ${f.lam_against.toFixed(1)}`}
              className="flex flex-col overflow-hidden rounded-lg border border-black/[.06] dark:border-white/[.06]"
            >
              {/* who they play — opponent colour + code + venue */}
              <span className="flex items-center gap-1 bg-black/5 px-[5px] py-[3px] dark:bg-white/10">
                <span
                  className="h-[9px] w-[9px] flex-none rounded-sm border border-black/20"
                  style={{ background: opp.primary }}
                />
                <span className="truncate font-mono text-[10px] font-semibold">{opp.shortCode}</span>
                <span className="ml-auto flex-none text-[9px] font-semibold text-black/45 dark:text-white/45">
                  {f.home ? "(H)" : "(A)"}
                </span>
              </span>

              <SplitCell attack={f.attack_fdr} defence={f.defence_fdr} lens={lens} />
            </span>
          );
        })}
      </span>
    </td>
  );
}

// --- one team row -------------------------------------------------------------------- //
function TeamRow({
  teamName,
  fixtures,
  gws,
  lastServed,
  horizon,
  lens,
  cellW,
}: {
  teamName: string;
  fixtures: TickerFixture[];
  gws: number[];
  lastServed: number;
  horizon: number;
  lens: TickerLens;
  cellW: string;
}) {
  const club = getClub(teamName);
  return (
    <tr className="group">
      {/* sticky team column — an opaque background is mandatory or the scrolled columns
          bleed through underneath it */}
      <td
        className={`sticky left-0 z-10 ${TEAM_W} border-r border-t border-black/10 bg-[var(--background)] p-0 dark:border-white/10`}
      >
        <span
          className="flex items-center gap-[7px] border-l-[3px] py-1.5 pr-2.5 group-hover:bg-black/[.02] dark:group-hover:bg-white/[.03]"
          style={{ borderLeftColor: club.primary }}
        >
          <Jersey
            primary={club.primary}
            secondary={club.secondary}
            pattern={club.pattern}
            width={22}
            height={21}
            className="ml-[7px] block flex-none"
          />
          <span className="flex min-w-0 items-center gap-1.5">
            <span className="font-mono text-xs font-semibold">{club.shortCode}</span>
            <span className="truncate text-[11px] text-black/50 dark:text-white/50">{teamName}</span>
          </span>
        </span>
      </td>

      {gws.map((g) => (
        <FixtureCell
          key={g}
          gw={g}
          fixtures={fixtures.filter((f) => f.gw === g)}
          teamName={teamName}
          lastServed={lastServed}
          horizon={horizon}
          lens={lens}
          cellW={cellW}
        />
      ))}
    </tr>
  );
}

// --- the grid ------------------------------------------------------------------------ //
function TickerGrid({
  rows,
  gws,
  lastServed,
  horizon,
  lens,
  cellW,
}: {
  rows: { team_id: number; team_name: string; fixtures: TickerFixture[] }[];
  gws: number[];
  lastServed: number;
  horizon: number;
  lens: TickerLens;
  cellW: string;
}) {
  return (
    // BOTH axes scroll here, and the height MUST be bounded. A `top`-sticky <th> pins to its
    // nearest scrolling ancestor, and overflow-x already makes this div one (CSS computes
    // overflow-y to auto too). Leave the height unbounded and the header has zero scroll
    // range inside the box — it scrolls away with the page instead of pinning.
    <div className="max-h-[calc(100vh-240px)] min-h-[300px] max-w-full overflow-auto overscroll-contain rounded-2xl border border-black/10 shadow-sm dark:border-white/10">
      <table className="w-max min-w-full border-separate border-spacing-0">
        <thead>
          <tr>
            {/* corner: sticky on BOTH axes, so it outranks the other two */}
            <th
              className={`sticky left-0 top-0 z-30 ${TEAM_W} border-b border-r border-black/10 bg-[var(--background)] px-2.5 py-[7px] text-left text-[10px] font-semibold uppercase tracking-[.06em] text-black/40 dark:border-white/10 dark:text-white/40`}
            >
              Team
            </th>
            {gws.map((g) => (
              <th
                key={g}
                className={`sticky top-0 z-20 ${cellW} border-b border-black/10 bg-[var(--background)] px-1 py-[7px] text-center text-[10px] font-semibold uppercase tracking-[.05em] dark:border-white/10 ${
                  g <= lastServed
                    ? "text-black/40 dark:text-white/40"
                    : "text-black/20 dark:text-white/20"
                }`}
              >
                GW{g}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((t) => (
            <TeamRow
              key={t.team_id}
              teamName={t.team_name}
              fixtures={t.fixtures}
              gws={gws}
              lastServed={lastServed}
              horizon={horizon}
              lens={lens}
              cellW={cellW}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

// --- the page's one client component ------------------------------------------------- //
export function FixtureTicker({ data }: { data: FixturesResponse }) {
  const [win, setWin] = useState<Win>(5);
  const [lens, setLens] = useState<TickerLens>("overall");

  const startGw = data.start_gw;
  const gws = Array.from({ length: win }, (_, i) => startGw + i);
  const windowEnd = startGw + win;

  // What this payload actually carries, taken from the data rather than assumed: a gameweek
  // past this is "pending", one at or before it with no fixture is a real blank.
  const lastServed = useMemo(() => {
    const all = data.teams.flatMap((t) => t.fixtures.map((f) => f.gw));
    return all.length ? Math.max(...all) : 0;
  }, [data.teams]);
  const horizon = data.meta.horizon ?? Math.max(lastServed - startGw + 1, 0);

  // Ranked by the mean FDR over the VISIBLE window, so the order follows the window too.
  // Overall ranks on both tracks at once; ties break alphabetically.
  const rows = useMemo(() => {
    const mean = (fx: TickerFixture[], key: "attack_fdr" | "defence_fdr") =>
      fx.length ? fx.reduce((s, f) => s + f[key], 0) / fx.length : 99; // 99 sinks empty rows
    return data.teams
      .map((t) => {
        const inWindow = t.fixtures.filter((f) => f.gw < windowEnd);
        return { ...t, atk: mean(inWindow, "attack_fdr"), def: mean(inWindow, "defence_fdr") };
      })
      .sort((a, b) => {
        const key =
          lens === "attack"
            ? a.atk - b.atk
            : lens === "defence"
              ? a.def - b.def
              : a.atk + a.def - (b.atk + b.def);
        return key || a.team_name.localeCompare(b.team_name);
      });
  }, [data.teams, lens, windowEnd]);

  const footnote =
    lastServed === 0
      ? "No fixtures in this payload yet."
      : windowEnd - 1 > lastServed
        ? `Showing GW${startGw}–${windowEnd - 1}; this payload carries GW${startGw}–${lastServed} (meta.horizon ${horizon}). GW${lastServed + 1}+ show as pending — re-run the precompute at its default horizon of 8 to fill them.`
        : `Showing GW${startGw}–${windowEnd - 1} of the model's ${lastServed - startGw + 1}-gameweek window. Difficulty is the model's expected goals, banded 1–5.`;

  return (
    <div className="flex flex-col gap-3.5">
      <FdrLegend lens={lens} />
      <TickerControls win={win} setWin={setWin} lens={lens} setLens={setLens} />
      <TickerGrid
        rows={rows}
        gws={gws}
        lastServed={lastServed}
        horizon={horizon}
        lens={lens}
        cellW={CELL_W[win]}
      />
      <p className="text-[11px] leading-relaxed text-black/40 dark:text-white/40">{footnote}</p>
    </div>
  );
}
