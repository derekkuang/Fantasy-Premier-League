"use client";
// One match (HANDOFF §40): the odds, the predicted lineups, and the FPL picks it holds.
//
// Everything here is a number the engine already produced; nothing is written by a model. The
// lineups are our minutes model's eleven in the shape the club has started with most in its
// last five matches, each player tagged by those starts, so a reader can see how settled a side
// is rather than take one guess on trust.

import { useMemo, useState } from "react";
import type { LineupPlayer, Match, Prediction, ProjectedLineup } from "@/lib/api";
import { getClub } from "@/lib/clubs";
import { POS_ORDER } from "@/lib/formation";
import { pct, roleOf } from "@/lib/odds";
import { Jersey } from "@/components/jersey";
import { Explained } from "@/components/explained";
import { Fold } from "@/components/fold";
import { PitchFrame } from "@/components/pitch";
import { PlayerSheet } from "@/components/player-sheet";
import { Segmented } from "@/components/segmented";

type Side = "home" | "away";

// --- the odds ------------------------------------------------------------------------ //
function ResultBar({ m }: { m: Match }) {
  const home = getClub(m.home), away = getClub(m.away);
  const parts = [
    { key: "home", label: home.shortCode, full: m.home, p: m.result.home_win, colour: home.primary, club: home },
    { key: "draw", label: "Draw", full: "Draw", p: m.result.draw, colour: "color-mix(in srgb, var(--muted) 45%, transparent)", club: null },
    { key: "away", label: away.shortCode, full: m.away, p: m.result.away_win, colour: away.primary, club: away },
  ];
  return (
    <section aria-label="Result chances" className="flex flex-col gap-2">
      <div className="grid grid-cols-3 items-end">
        {parts.map((x, i) => (
          <div key={x.key} className={`flex flex-col gap-0.5 ${i === 0 ? "items-start" : i === 1 ? "items-center" : "items-end"}`}>
            <span className="flex items-center gap-1.5 text-[13px] text-muted">
              {x.club && <Jersey primary={x.club.primary} secondary={x.club.secondary} pattern={x.club.pattern} width={18} height={17} className="block flex-none" />}
              <span className="sm:hidden">{x.label}</span>
              <span className="hidden sm:inline">{x.full}</span>
            </span>
            <span className="t-title text-[24px] font-bold leading-none tabular-nums">{pct(x.p)}</span>
          </div>
        ))}
      </div>
      <div className="flex h-2.5 gap-[2px] overflow-hidden rounded-full" aria-hidden>
        {parts.map((x) => (
          <span key={x.key} className="h-full ring-1 ring-inset ring-black/10 dark:ring-white/15"
            style={{ width: `${x.p * 100}%`, background: x.colour }} />
        ))}
      </div>
    </section>
  );
}

function Tile({ value, label }: { value: string; label: string }) {
  return (
    <div className="flex flex-col gap-1 rounded-[12px] border border-[var(--line)] px-3 py-2.5">
      <span className="t-title text-[20px] font-bold leading-none tabular-nums">{value}</span>
      <span className="text-[12px] text-muted">{label}</span>
    </div>
  );
}

function OddsTiles({ m }: { m: Match }) {
  const h = getClub(m.home).shortCode, a = getClub(m.away).shortCode;
  const [hs, as] = m.most_likely_score;
  const top = m.scorelines[0]?.p;
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      <Tile value={`${hs}–${as}`} label={top != null ? `Most likely score, ${pct(top)}` : "Most likely score"} />
      <Tile value={`${m.lam_home.toFixed(1)} – ${m.lam_away.toFixed(1)}`} label={`Expected goals, ${h} – ${a}`} />
      <Tile value={`${pct(m.clean_sheet.home)} · ${pct(m.clean_sheet.away)}`} label={`Clean sheet, ${h} · ${a}`} />
      <Tile value={pct(m.over_2_5)} label={`Over 2.5 goals · both score ${pct(m.btts)}`} />
    </div>
  );
}

// --- the predicted lineups ------------------------------------------------------------- //
const TONE = {
  good: "bg-emerald-50 text-emerald-800",
  mid: "bg-amber-100 text-amber-900",
  bad: "bg-rose-100 text-rose-900",
} as const;

/** FPL's own flag first (it is the more current fact), then what his recent starts say. */
function tagFor(p: LineupPlayer): { text: string; cls: string; title: string } | null {
  if (p.status === "d" || (p.chance != null && p.chance < 100)) {
    return { text: `${p.chance ?? "?"}%`, cls: TONE.mid, title: `${p.chance ?? "?"}% chance of playing, per FPL` };
  }
  const role = roleOf(p.starts);
  if (!role || !p.starts) return null;
  return { text: role.word, cls: TONE[role.tone], title: `Started ${p.starts[0]} of his club's last ${p.starts[1]}` };
}

function LineupToken({ p, team, onOpen }: { p: LineupPlayer; team: string | null; onOpen: () => void }) {
  const club = getClub(team);
  const tag = tagFor(p);
  return (
    <button type="button" onClick={onOpen} title={`${p.web_name}${tag ? ` · ${tag.title}` : ""} · tap for detail`}
      className="press flex min-w-0 max-w-[84px] flex-1 flex-col items-center gap-1 rounded-[10px] pt-0.5 text-inherit hover:bg-white/[.09] focus-visible:ring-2 focus-visible:ring-white/60">
      <Jersey primary={club.primary} secondary={club.secondary} pattern={club.pattern} width={38} height={36}
        className="block [filter:drop-shadow(0_2px_3px_rgba(0,0,0,.3))]" />
      <span className="max-w-full truncate rounded-full bg-black/60 px-[7px] py-0.5 text-[12px] font-semibold text-white">{p.web_name}</span>
      {tag && <span className={`rounded px-[5px] text-[11px] font-bold ${tag.cls}`}>{tag.text}</span>}
    </button>
  );
}

function LineupCard({ team, lineup, onOpen }: { team: string | null; lineup: ProjectedLineup | null | undefined; onOpen: (id: number) => void }) {
  const club = getClub(team);
  if (!lineup) {
    return <p className="rounded-2xl border border-[var(--line)] p-4 text-[14px] text-muted">{`No predicted lineup for ${team ?? "this side"} yet.`}</p>;
  }
  const rows = POS_ORDER.map((pos) => lineup.xi.filter((p) => p.position === pos)).filter((r) => r.length);
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <div className="flex items-center justify-between gap-2 px-0.5">
        <span className="flex min-w-0 items-center gap-2">
          <Jersey primary={club.primary} secondary={club.secondary} pattern={club.pattern} width={20} height={19} className="block flex-none" />
          <span className="truncate text-[14px] font-semibold">{team}</span>
        </span>
        <span title={lineup.basis === "recent" ? "The shape this club has started with most in its last five matches" : "The legal shape with the most expected minutes"}
          className="flex-none rounded-full bg-emerald-600 px-2.5 py-1 text-[11px] font-bold tabular-nums text-white">
          {lineup.formation}
        </span>
      </div>
      <PitchFrame>
        <ol className="relative flex min-h-[400px] flex-col justify-between gap-2 px-1.5 pb-4 pt-3">
          {rows.map((row) => (
            <li key={row[0].position} className="flex min-w-0 items-start justify-center gap-0.5">
              {row.map((p) => <LineupToken key={p.element_id} p={p} team={team} onOpen={() => onOpen(p.element_id)} />)}
            </li>
          ))}
        </ol>
      </PitchFrame>
      {lineup.bench.length > 0 && (
        <p className="flex flex-wrap items-center gap-1.5 text-[13px]">
          <span className="text-muted">Next in line</span>
          {lineup.bench.map((p) => (
            <button key={p.element_id} type="button" onClick={() => onOpen(p.element_id)}
              className="press rounded-full border border-[var(--line)] px-2.5 py-0.5 text-[12px] font-semibold hover:border-emerald-600">
              {p.web_name}
            </button>
          ))}
        </p>
      )}
    </div>
  );
}

function Lineups({ m, onOpen }: { m: Match; onOpen: (id: number) => void }) {
  const [side, setSide] = useState<Side>("home");
  const sides: { key: Side; team: string | null; lineup: ProjectedLineup | null | undefined }[] = [
    { key: "home", team: m.home, lineup: m.lineups?.home },
    { key: "away", team: m.away, lineup: m.lineups?.away },
  ];
  return (
    <section className="flex flex-col gap-3">
      <h2 className="t-title text-[17px] font-semibold">Predicted lineups</h2>
      <Explained label="How are these picked?"
        head={<span className="text-[13px] text-muted">From our minutes model, in each club&apos;s usual shape.</span>}>
        {"Each eleven is the players our minutes model expects to play most, in the shape (defenders, " +
          "midfielders and forwards, by FPL position) the club has started with most in its last five " +
          "matches. That shape matched the next match's 66 times in 100 this season. It's a model, not team " +
          "news. The tags come from starts in those five matches: of players who had started all five, 91% " +
          "started the next match (Nailed); four of five, 64% (Regular); one to three, 29–51% (Rotation); " +
          "none, 4%. A percentage is FPL's own chance of playing."}
      </Explained>
      <Segmented label="Which side" className="self-start lg:hidden"
        options={[["home", m.home ?? "Home"], ["away", m.away ?? "Away"]] as const} value={side} onChange={setSide} />
      <div className="grid gap-4 lg:grid-cols-2">
        {sides.map((s) => (
          <div key={s.key} className={s.key === side ? "" : "hidden lg:block"}>
            <LineupCard team={s.team} lineup={s.lineup} onOpen={onOpen} />
          </div>
        ))}
      </div>
    </section>
  );
}

// --- the FPL picks ----------------------------------------------------------------------- //
function Picks({ assets, onOpen }: { assets: Prediction[]; onOpen: (id: number) => void }) {
  const top = assets.slice(0, 6);
  return (
    <section className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="t-title text-[17px] font-semibold">Best FPL picks from this match</h2>
        <span className="text-[13px] text-muted">expected points</span>
      </div>
      <ul className="flex flex-col rounded-2xl border border-[var(--line)] px-4">
        {top.map((p) => {
          const club = getClub(p.team);
          return (
            <li key={p.element_id} className="border-t border-[var(--line)] first:border-t-0">
              <button type="button" onClick={() => onOpen(p.element_id)}
                className="press flex w-full items-center gap-2.5 py-2.5 text-left text-inherit">
                <Jersey primary={club.primary} secondary={club.secondary} pattern={club.pattern} width={22} height={21} className="block flex-none" />
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate text-[14px] font-semibold">{p.web_name}</span>
                  <span className="text-[12px] tabular-nums text-muted">
                    {`${club.shortCode} · ${p.position} · £${p.price.toFixed(1)}m · ${p.ownership.toFixed(1)}% owned`}
                  </span>
                </span>
                <span className="t-title flex-none text-[17px] font-bold tabular-nums" style={{ color: "var(--emerald-text)" }}>
                  {p.xp.toFixed(1)}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function Scorelines({ m }: { m: Match }) {
  const rows = m.scorelines.slice(0, 6);
  const max = Math.max(...rows.map((r) => r.p), 0.0001);
  const h = getClub(m.home).shortCode, a = getClub(m.away).shortCode;
  return (
    <Fold title="Likeliest scores" aside={`${h} – ${a}`}>
      <ul className="flex flex-col gap-1.5 pt-1">
        {rows.map((r) => (
          <li key={`${r.home}-${r.away}`} className="grid grid-cols-[48px_1fr_44px] items-center gap-2 text-[13px] tabular-nums">
            <span className="font-semibold">{`${r.home}–${r.away}`}</span>
            <span className="h-2 overflow-hidden rounded-full bg-[var(--chip)]">
              <span className="block h-full rounded-full bg-emerald-600" style={{ width: `${(r.p / max) * 100}%` }} />
            </span>
            <span className="text-right text-muted">{pct(r.p)}</span>
          </li>
        ))}
      </ul>
      <p className="pt-2 text-[12px] text-muted">
        {`No single score is likely: these six cover ${pct(rows.reduce((s, r) => s + r.p, 0))} of outcomes between them.`}
      </p>
    </Fold>
  );
}

// --- the page's one client component -------------------------------------------------- //
export function MatchLab({ match, assets, gw }: { match: Match; assets: Prediction[]; gw: number }) {
  const [openId, setOpenId] = useState<number | null>(null);
  const byId = useMemo(() => new Map(assets.map((p) => [p.element_id, p])), [assets]);
  const open = openId != null ? byId.get(openId) : undefined;
  const onOpen = (id: number) => { if (byId.has(id)) setOpenId(id); };
  const thisWeek = match.gw === gw;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3">
        <ResultBar m={match} />
        <OddsTiles m={match} />
      </div>
      {thisWeek ? (
        <>
          <Lineups m={match} onOpen={onOpen} />
          {assets.length > 0 && <Picks assets={assets} onOpen={onOpen} />}
        </>
      ) : (
        <p className="rounded-2xl border border-[var(--line)] p-4 text-[14px] text-muted">
          {`Predicted lineups and the best picks appear in gameweek ${match.gw}, once it's the next one.`}
        </p>
      )}
      <Scorelines m={match} />
      {open && <PlayerSheet player={open} gw={gw} onClose={() => setOpenId(null)} />}
    </div>
  );
}
