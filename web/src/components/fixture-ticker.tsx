"use client";
// True-FDR fixture ticker: teams down, gameweeks across, one coloured number per fixture.
//
// The lens decides both what each cell shows and how the rows are ranked. "Overall" is
// difficulty, attack and defence averaged, and ranks by both; Win %, Goals and Clean sheet print
// that chance in every cell and rank by it (HANDOFF §40). Every fixture opens its match page. On
// a phone the team column is just the club code, so five gameweeks fit on screen.
//
// The grid is its own two-axis scroll region so the page never scrolls sideways, and both
// sticky axes have a scroll range to pin against.

import Link from "next/link";
import { useMemo, useState } from "react";
import type { FixturesResponse, TickerFixture } from "@/lib/api";
import { oddsKey, pct, type FixtureOdds } from "@/lib/odds";
import { fdrColour, fdrGlyph, getClub } from "@/lib/clubs";
import { Jersey } from "@/components/jersey";
import { Explained } from "@/components/explained";
import { oppLabel } from "@/components/season-history";
import { SplitCell, type TickerLens } from "@/components/split-cell";

type Odds = Record<string, FixtureOdds>;
import { Segmented } from "@/components/segmented";

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


// --- legend: one line, the rest behind "i" ------------------------------------------- //
function FdrLegend({ hasMarket, lens }: { hasMarket: boolean; lens: TickerLens }) {
  const overall = lens === "overall";
  return (
    <Explained
      label="How are these worked out?"
      head={
        <div className="flex items-center gap-1.5 text-[13px] text-muted">
          <span>{overall ? "Easy" : "Better"}</span>
          {[1, 2, 3, 4, 5].map((n) => (
            <span
              key={n}
              className="grid h-5 w-5 place-items-center rounded-[5px] text-[11px] font-bold tabular-nums"
              style={{ background: fdrColour(n), color: fdrGlyph(n) }}
            >
              {overall ? n : ""}
            </span>
          ))}
          <span>{overall ? "Hard" : "Worse"}</span>
        </div>
      }
    >
      {"Overall is difficulty from 1 (easy) to 5 (hard): how likely a team is to score and to keep a " +
        "clean sheet, averaged. The other views print the chance itself: Win % to win the match, Goals " +
        "the goals it's expected to score, Clean sheet the chance of keeping one. Attackers want Goals, " +
        "defenders and keepers want Clean sheet. Home fixtures are in capitals. Tap any fixture for its " +
        "match page: the odds, the likely scores and both predicted lineups. "}
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
    <div className="flex flex-wrap items-center gap-2">
      <Segmented label="How many gameweeks" options={[[3, "Next 3"], [5, "Next 5"], [8, "Next 8"]] as const} value={win} onChange={setWin} />
      <Segmented
        label="Which difficulty"
        options={[["overall", "Overall"], ["win", "Win %"], ["goals", "Goals"], ["cs", "Clean sheet"]] as const}
        value={lens}
        onChange={setLens}
      />
    </div>
  );
}

// --- one gameweek cell for one team -------------------------------------------------- //
function FixtureCell({
  fixtures,
  gw,
  teamId,
  teamName,
  lastServed,
  horizon,
  lens,
  odds,
  cellW,
}: {
  fixtures: TickerFixture[];
  gw: number;
  teamId: number;
  teamName: string;
  lastServed: number;
  horizon: number;
  lens: TickerLens;
  odds: Odds;
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
          const o = odds[oddsKey(f.gw, teamId, f.opp_id)];
          const title = `GW${f.gw} v ${f.opp} (${f.home ? "home" : "away"}): ` +
            (o ? `win ${pct(o.win)}, clean sheet ${pct(o.cs)}, ` : "") +
            `${f.lam_for.toFixed(1)} goals expected, ${f.source === "market" ? "from bookmaker odds" : "from the match model"}`;
          const body = (
            <>
              {/* who they play: home in capitals, away in lower case */}
              <span className="truncate bg-black/[.04] px-1 py-[3px] text-center font-mono text-[12px] font-semibold dark:bg-white/[.07]">
                {oppLabel(f.opp, f.home)}
              </span>
              <SplitCell fixture={f} odds={o} lens={lens} />
            </>
          );
          const tile = "flex flex-col overflow-hidden rounded-lg border border-[var(--line)]";
          // Not prefetched: a hundred visible cells would each fetch a match page.
          return o ? (
            <Link key={`${f.opp}-${f.home}`} href={`/match-lab/${o.id}`} prefetch={false} title={title}
              className={`${tile} press hover:border-emerald-600 focus-visible:ring-2 focus-visible:ring-emerald-600`}>
              {body}
            </Link>
          ) : (
            <span key={`${f.opp}-${f.home}`} title={title} className={tile}>{body}</span>
          );
        })}
      </span>
    </td>
  );
}

// --- one team row -------------------------------------------------------------------- //
function TeamRow({
  teamId,
  teamName,
  fixtures,
  gws,
  lastServed,
  horizon,
  lens,
  odds,
  cellW,
}: {
  teamId: number;
  teamName: string;
  fixtures: TickerFixture[];
  gws: number[];
  lastServed: number;
  horizon: number;
  lens: TickerLens;
  odds: Odds;
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
          teamId={teamId}
          teamName={teamName}
          lastServed={lastServed}
          horizon={horizon}
          lens={lens}
          odds={odds}
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
  odds,
  cellW,
}: {
  rows: { team_id: number; team_name: string; fixtures: TickerFixture[] }[];
  gws: number[];
  lastServed: number;
  horizon: number;
  lens: TickerLens;
  odds: Odds;
  cellW: string;
}) {
  return (
    // BOTH axes scroll here, and the height MUST be bounded. A `top`-sticky <th> pins to its
    // nearest scrolling ancestor, and overflow-x already makes this div one (CSS computes
    // overflow-y to auto too). Leave the height unbounded and the header has zero scroll
    // range inside the box — it scrolls away with the page instead of pinning.
    <div className="scroll-thin max-h-[calc(100vh-240px)] min-h-[300px] max-w-full overflow-auto overscroll-contain rounded-2xl border border-[var(--line)] lg:max-h-[calc(100vh-190px)]">
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
              teamId={t.team_id}
              teamName={t.team_name}
              fixtures={t.fixtures}
              gws={gws}
              lastServed={lastServed}
              horizon={horizon}
              lens={lens}
              odds={odds}
              cellW={cellW}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

// --- the page's one client component ------------------------------------------------- //
export function FixtureTicker({ data, odds }: { data: FixturesResponse; odds: Odds }) {
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

  // Ranked over the VISIBLE window, so the order follows the window too: Overall by mean
  // difficulty (both tracks at once), the others by the mean chance, best first. Ties break
  // alphabetically; a team with nothing in the window sinks.
  const rows = useMemo(() => {
    const score = (t: { team_id: number; fixtures: TickerFixture[] }): number => {
      const fx = t.fixtures.filter((f) => f.gw < windowEnd);
      if (!fx.length) return Infinity;
      const mean = (get: (f: TickerFixture) => number) => fx.reduce((s, f) => s + get(f), 0) / fx.length;
      const chance = (get: (o: FixtureOdds) => number) =>
        -mean((f) => { const o = odds[oddsKey(f.gw, t.team_id, f.opp_id)]; return o ? get(o) : 0; });
      switch (lens) {
        case "overall": return mean((f) => f.attack_fdr + f.defence_fdr);
        case "goals": return -mean((f) => f.lam_for);
        case "win": return chance((o) => o.win);
        case "cs": return chance((o) => o.cs);
      }
    };
    return data.teams
      .map((t) => ({ ...t, score: score(t) }))
      .sort((a, b) => (a.score === b.score ? 0 : a.score - b.score) || a.team_name.localeCompare(b.team_name));
  }, [data.teams, lens, windowEnd, odds]);

  const footnote = lastServed === 0 ? "No fixtures have been projected yet." : null;

  return (
    <div className="flex flex-col gap-3.5">
      <TickerControls win={win} setWin={setWin} lens={lens} setLens={setLens} />
      <FdrLegend hasMarket={hasMarket} lens={lens} />
      <TickerGrid
        rows={rows}
        gws={gws}
        lastServed={lastServed}
        horizon={horizon}
        lens={lens}
        odds={odds}
        cellW={CELL_W[win]}
      />
      {footnote && <p className="text-[13px] text-muted">{footnote}</p>}
    </div>
  );
}
