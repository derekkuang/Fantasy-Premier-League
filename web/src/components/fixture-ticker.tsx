"use client";
// True-FDR fixture ticker: teams down, gameweeks across, one coloured number per fixture.
//
// The lens decides both what each cell shows and how the rows are ranked. "Overall" averages
// attack (chance to score) and defence (chance of a clean sheet) and ranks by both; Attack or
// Defence narrows every cell to that track and ranks by it. On a phone the team column is just
// the club code, so five gameweeks fit on screen.
//
// The grid is its own two-axis scroll region so the page never scrolls sideways, and both
// sticky axes have a scroll range to pin against.

import { useMemo, useState } from "react";
import type { FixturesResponse, TickerFixture } from "@/lib/api";
import { fdrColour, fdrGlyph, getClub } from "@/lib/clubs";
import { Jersey } from "@/components/jersey";
import { Explained } from "@/components/explained";
import { oppLabel } from "@/components/season-history";
import { SplitCell, type TickerLens } from "@/components/split-cell";

type Win = 3 | 5 | 8;

// Cell width scales with the window so a short window doesn't leave dead space. These must
// be literal class strings — Tailwind scans source text, so a template-built class never
// generates any CSS.
const CELL_W: Record<Win, string> = {
  3: "w-[96px] min-w-[96px] sm:w-[116px] sm:min-w-[116px] lg:w-[168px] lg:min-w-[168px]",
  5: "w-[58px] min-w-[58px] sm:w-[96px] sm:min-w-[96px] lg:w-[132px] lg:min-w-[132px]",
  8: "w-[56px] min-w-[56px] sm:w-[80px] sm:min-w-[80px] lg:w-[104px] lg:min-w-[104px]",
};
const TEAM_W = "w-[64px] min-w-[64px] sm:w-[132px] sm:min-w-[132px] lg:w-[150px] lg:min-w-[150px]";

const PILL = "press min-h-9 cursor-pointer rounded-full border px-3 py-1.5 text-[13px] font-semibold";
const PILL_ON = "border-emerald-600 bg-emerald-600 text-white";
const PILL_OFF = "border-[var(--line)] text-muted hover:text-[var(--fg)]";

const LENS_HINT: Record<TickerLens, string> = {
  overall: "attack and defence averaged",
  attack: "how likely they are to score",
  defence: "how likely a clean sheet is",
};

// --- legend: one line, the rest behind "i" ------------------------------------------- //
function FdrLegend({ hasMarket }: { hasMarket: boolean }) {
  return (
    <Explained
      label="How is difficulty worked out?"
      head={
        <div className="flex items-center gap-1.5 text-[13px] text-muted">
          <span>Easy</span>
          {[1, 2, 3, 4, 5].map((n) => (
            <span
              key={n}
              className="grid h-5 w-5 place-items-center rounded-[5px] text-[11px] font-bold tabular-nums"
              style={{ background: fdrColour(n), color: fdrGlyph(n) }}
            >
              {n}
            </span>
          ))}
          <span>Hard</span>
        </div>
      }
    >
      Attack is how likely a team is to score; defence is how likely it keeps a clean sheet.
      Overall averages the two, and they often disagree, so switch to one when you&apos;re
      picking attackers or defenders. Home fixtures are in capitals.{" "}
      {hasMarket
        ? "The nearest gameweeks use bookmaker odds where a match is priced; later ones use the match model."
        : "Every fixture here comes from the match model; no bookmaker prices cover this window yet."}
    </Explained>
  );
}

// --- controls -------------------------------------------------------------------- //
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
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <div className="flex gap-1.5" role="group" aria-label="How many gameweeks">
        {([3, 5, 8] as const).map((w) => (
          <button key={w} onClick={() => setWin(w)} aria-pressed={win === w} className={`${PILL} ${win === w ? PILL_ON : PILL_OFF}`}>
            {`Next ${w}`}
          </button>
        ))}
      </div>
      <div className="flex gap-1.5" role="group" aria-label="Which difficulty">
        {(["overall", "attack", "defence"] as const).map((l) => (
          <button
            key={l}
            onClick={() => setLens(l)}
            title={LENS_HINT[l]}
            aria-pressed={lens === l}
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
  const cls = `${cellW} border-t border-[var(--line)] p-[3px] align-top`;

  if (!fixtures.length && gw <= lastServed) {
    // A genuine blank gameweek — real, and worth distinguishing from missing data.
    return (
      <td className={cls}>
        <span
          title={`GW${gw} — blank gameweek for ${teamName}`}
          className="flex h-11 items-center justify-center rounded-lg border border-dashed border-[var(--line)] text-[13px] text-muted"
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
          title={`GW${gw} isn't projected yet (the projections run ${horizon} gameweeks ahead)`}
          className="flex h-11 items-center justify-center rounded-lg border border-dashed border-[var(--line)] text-[11px] text-muted"
        >
          later
        </span>
      </td>
    );
  }

  return (
    <td className={cls}>
      <span className="flex flex-col gap-0.5">
        {/* a double gameweek stacks two tiles in the one column */}
        {fixtures.map((f) => {
          return (
            <span
              key={`${f.opp}-${f.home}`}
              title={`GW${f.gw} v ${f.opp} (${f.home ? "home" : "away"}): attack ${f.attack_fdr}, defence ${f.defence_fdr}, ${f.source === "market" ? "from bookmaker odds" : "from the match model"}`}
              className="flex flex-col overflow-hidden rounded-lg border border-[var(--line)]"
            >
              {/* who they play: home in capitals, away in lower case */}
              <span className="truncate bg-black/[.04] px-1 py-[3px] text-center font-mono text-[12px] font-semibold dark:bg-white/[.07]">
                {oppLabel(f.opp, f.home)}
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
        className={`sticky left-0 z-10 ${TEAM_W} border-r border-t border-[var(--line)] bg-[var(--background)] p-0`}
      >
        <span
          title={teamName}
          className="flex items-center gap-1.5 border-l-[3px] py-1.5 pr-1.5 group-hover:bg-black/[.02] dark:group-hover:bg-white/[.03]"
          style={{ borderLeftColor: club.primary }}
        >
          <Jersey
            primary={club.primary}
            secondary={club.secondary}
            pattern={club.pattern}
            width={18}
            height={17}
            className="ml-1.5 block flex-none"
          />
          <span className="flex min-w-0 items-center gap-1.5">
            <span className="font-mono text-[12px] font-semibold">{club.shortCode}</span>
            <span className="hidden truncate text-[12px] text-muted sm:inline">{teamName}</span>
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
    <div className="max-h-[calc(100vh-240px)] min-h-[300px] max-w-full overflow-auto overscroll-contain rounded-2xl border border-[var(--line)]">
      <table className="w-max min-w-full border-separate border-spacing-0">
        <thead>
          <tr>
            {/* corner: sticky on BOTH axes, so it outranks the other two */}
            <th
              className={`sticky left-0 top-0 z-30 ${TEAM_W} border-b border-r border-[var(--line)] bg-[var(--background)] px-2 py-[7px] text-left text-[12px] font-semibold text-muted`}
            >
              Team
            </th>
            {gws.map((g) => (
              <th
                key={g}
                className={`sticky top-0 z-20 ${cellW} border-b border-[var(--line)] bg-[var(--background)] px-1 py-[7px] text-center text-[12px] font-semibold text-muted`}
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

  // Whether ANY cell in this payload came from a betting line. Drives the legend, so the page
  // describes the artifact it is actually rendering.
  const hasMarket = useMemo(
    () => data.teams.some((t) => t.fixtures.some((f) => f.source === "market")),
    [data.teams],
  );

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

  const footnote = lastServed === 0 ? "No fixtures have been projected yet." : null;

  return (
    <div className="flex flex-col gap-3.5">
      <TickerControls win={win} setWin={setWin} lens={lens} setLens={setLens} />
      <FdrLegend hasMarket={hasMarket} />
      <TickerGrid
        rows={rows}
        gws={gws}
        lastServed={lastServed}
        horizon={horizon}
        lens={lens}
        cellW={CELL_W[win]}
      />
      {footnote && <p className="text-[13px] text-muted">{footnote}</p>}
    </div>
  );
}
