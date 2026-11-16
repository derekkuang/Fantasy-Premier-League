"use client";
// The Match Lab hub's cards (docs/MATCH_LAB.md): a gameweek at a time, sortable, each card a link
// to the match. The cards carry a summary built on the server, never the full player list.

import Link from "next/link";
import { useMemo, useState } from "react";
import type { Match } from "@/lib/api";
import { getClub } from "@/lib/clubs";
import { DISAGREE, kickoffLabel } from "@/lib/match-lab";
import { pct } from "@/lib/odds";
import { Jersey } from "@/components/jersey";
import { Segmented } from "@/components/segmented";

export type HubPick = { id: number; name: string; xp: number };
export type HubMatch = {
  id: string;
  gw: number;
  home: string | null;
  away: string | null;
  kickoff: string | null;
  result: Match["result"];
  lam_home: number;
  lam_away: number;
  clean_sheet: Match["clean_sheet"];
  source: Match["source"];
  gap: number | null;
  flagged: { home: number | null; away: number | null };
  pick: { home: HubPick | null; away: HubPick | null };
};

type Sort = "kickoff" | "goals" | "cs" | "gap";
const SORTS = [["kickoff", "Kickoff"], ["goals", "Goals"], ["cs", "Clean sheet"], ["gap", "Model gap"]] as const;

function order(cards: HubMatch[], sort: Sort): HubMatch[] {
  const by: Record<Sort, (m: HubMatch) => number | string> = {
    kickoff: (m) => m.kickoff ?? "",
    goals: (m) => -(m.lam_home + m.lam_away),
    cs: (m) => -Math.max(m.clean_sheet.home, m.clean_sheet.away),
    gap: (m) => -(m.gap ?? -1),
  };
  const key = by[sort];
  return [...cards].sort((a, b) => {
    const x = key(a), y = key(b);
    return x < y ? -1 : x > y ? 1 : (a.home ?? "").localeCompare(b.home ?? "");
  });
}

function TeamLine({ team, p, pick }: { team: string | null; p: number; pick: HubPick | null }) {
  const club = getClub(team);
  return (
    <div className="flex min-w-0 items-center gap-2">
      <Jersey primary={club.primary} secondary={club.secondary} pattern={club.pattern} width={22} height={21} className="block flex-none" />
      <span className="min-w-0 flex-1 truncate text-[15px] font-semibold">{team}</span>
      {pick && <span className="hidden max-w-[45%] truncate text-[12px] text-muted sm:inline">{`${pick.name} ${pick.xp.toFixed(1)}`}</span>}
      <span className="t-title w-11 flex-none text-right text-[15px] font-bold tabular-nums">{pct(p)}</span>
    </div>
  );
}

function Card({ m }: { m: HubMatch }) {
  const home = getClub(m.home), away = getClub(m.away);
  const flagged = (m.flagged.home ?? 0) + (m.flagged.away ?? 0);
  const parts = [
    { key: "h", p: m.result.home_win, colour: home.primary },
    { key: "d", p: m.result.draw, colour: "color-mix(in srgb, var(--muted) 45%, transparent)" },
    { key: "a", p: m.result.away_win, colour: away.primary },
  ];
  const when = kickoffLabel(m.kickoff);
  return (
    <li>
      <Link href={`/match-lab/${m.id}`} prefetch={false}
        className="press flex h-full flex-col gap-2.5 rounded-2xl border border-[var(--line)] p-4 text-inherit hover:border-emerald-600 focus-visible:ring-2 focus-visible:ring-emerald-600">
        <div className="flex items-center justify-between gap-2 text-[12px] text-muted">
          <span>{when ?? `Gameweek ${m.gw}`}</span>
          <span>{m.source === "market" ? "bookmakers' odds" : "our model's odds"}</span>
        </div>
        <div className="flex flex-col gap-1.5">
          <TeamLine team={m.home} p={m.result.home_win} pick={m.pick.home} />
          <TeamLine team={m.away} p={m.result.away_win} pick={m.pick.away} />
        </div>
        <div className="flex h-1.5 gap-[2px] overflow-hidden rounded-full" aria-hidden>
          {parts.map((x) => <span key={x.key} className="h-full ring-1 ring-inset ring-black/10 dark:ring-white/15" style={{ width: `${x.p * 100}%`, background: x.colour }} />)}
        </div>
        <p className="text-[12px] tabular-nums text-muted">
          {`Draw ${pct(m.result.draw)} · expected goals ${m.lam_home.toFixed(1)}–${m.lam_away.toFixed(1)} · clean sheet ${pct(m.clean_sheet.home)} · ${pct(m.clean_sheet.away)}`}
        </p>
        {(m.pick.home || m.pick.away) && (
          <p className="truncate text-[12px] sm:hidden">
            <span className="text-muted">Best picks </span>
            {[m.pick.home, m.pick.away].filter(Boolean).map((p) => `${p!.name} ${p!.xp.toFixed(1)}`).join(" · ")}
          </p>
        )}
        {((m.gap != null && m.gap >= DISAGREE) || flagged > 0) && (
          <div className="flex flex-wrap gap-1.5">
            {m.gap != null && m.gap >= DISAGREE && (
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-bold text-amber-900">Our model disagrees</span>
            )}
            {flagged > 0 && (
              <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[11px] font-bold text-rose-900">
                {`${flagged} injured or doubtful`}
              </span>
            )}
          </div>
        )}
      </Link>
    </li>
  );
}

export function MatchHub({ cards, current }: { cards: HubMatch[]; current: number }) {
  const gws = useMemo(() => [...new Set(cards.map((c) => c.gw))].sort((a, b) => a - b), [cards]);
  const [gw, setGw] = useState(current);
  const [sort, setSort] = useState<Sort>("kickoff");
  const shown = useMemo(() => order(cards.filter((c) => c.gw === gw), sort), [cards, gw, sort]);
  const i = gws.indexOf(gw);
  const step = (d: number) => { const next = gws[i + d]; if (next != null) setGw(next); };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1" role="group" aria-label="Gameweek">
          <button type="button" onClick={() => step(-1)} disabled={i <= 0} aria-label="Previous gameweek"
            className="press grid h-9 w-9 place-items-center rounded-full border border-[var(--line)] disabled:opacity-35">‹</button>
          <span className="t-title min-w-[120px] text-center text-[15px] font-semibold tabular-nums">{`Gameweek ${gw}`}</span>
          <button type="button" onClick={() => step(1)} disabled={i >= gws.length - 1} aria-label="Next gameweek"
            className="press grid h-9 w-9 place-items-center rounded-full border border-[var(--line)] disabled:opacity-35">›</button>
        </div>
        <Segmented label="Sort matches" options={SORTS} value={sort} onChange={setSort} />
      </div>
      {gw !== current && (
        <p className="text-[13px] text-muted">{`Lineups, team news and picks come in gameweek ${gw}, once it's the next one.`}</p>
      )}
      <ul className="grid gap-3 sm:grid-cols-2">
        {shown.map((m) => <Card key={m.id} m={m} />)}
      </ul>
    </div>
  );
}
