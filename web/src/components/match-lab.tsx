"use client";
// One match in the Match Lab (HANDOFF §40, §45, docs/MATCH_LAB.md), in five sections behind a
// sticky strip: Overview (odds, the written read when one exists, our model's view, form), News
// (FPL's flags and the week's stories for both clubs), Lineups (predicted XIs, set-piece takers),
// FPL (the best picks and each player's chances) and Scores.
//
// Everything here is a number the engine already produced; nothing is written by a model. The
// lineups are our minutes model's eleven in the shape the club has started with most in its
// last five matches, each player tagged by those starts, so a reader can see how settled a side
// is rather than take one guess on trust.

import { useMemo, useState, type ReactNode } from "react";
import type { FormResult, LineupPlayer, Match, NewsResponse, Prediction, ProjectedLineup } from "@/lib/api";
import { getClub } from "@/lib/clubs";
import { POS_ORDER } from "@/lib/formation";
import { DIFFERENTIAL_OWNERSHIP, atLeastOne, isFlagged } from "@/lib/match-lab";
import { pct, roleOf } from "@/lib/odds";
import { Jersey } from "@/components/jersey";
import { Explained } from "@/components/explained";
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

// --- our model's second opinion ------------------------------------------------------- //
/** One sentence on where our engine and the bookmakers part ways, in expected goals. */
function disagreement(m: Match, mo: NonNullable<Match["model"]>): string {
  const sides = [
    { team: m.home ?? "the home side", book: m.lam_home, ours: mo.lam_home },
    { team: m.away ?? "the away side", book: m.lam_away, ours: mo.lam_away },
  ];
  const big = sides.reduce((x, y) => (Math.abs(y.ours - y.book) > Math.abs(x.ours - x.book) ? y : x));
  if (Math.abs(big.ours - big.book) < 0.2) return "Our model broadly agrees with the bookmakers.";
  const way = big.ours > big.book ? "more" : "fewer";
  return `Our model expects ${way} ${big.team} goals: ${big.ours.toFixed(1)} against the bookmakers' ${big.book.toFixed(1)}.`;
}

function SecondOpinion({ m }: { m: Match }) {
  const mo = m.model;
  if (m.source !== "market" || !mo) return null;
  const h = getClub(m.home).shortCode, a = getClub(m.away).shortCode;
  const rows: [string, string, string][] = [
    [`${h} expected goals`, m.lam_home.toFixed(1), mo.lam_home.toFixed(1)],
    [`${a} expected goals`, m.lam_away.toFixed(1), mo.lam_away.toFixed(1)],
    [`${h} win`, pct(m.result.home_win), pct(mo.result.home_win)],
    ["Draw", pct(m.result.draw), pct(mo.result.draw)],
    [`${a} win`, pct(m.result.away_win), pct(mo.result.away_win)],
  ];
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-[15px] font-semibold">Our model&apos;s view</h3>
      <Explained label="Why lead with the bookmakers?"
        head={<span className="text-[13px] text-muted">{disagreement(m, mo)}</span>}>
        {"The odds above are the bookmakers', with their margin taken out. Tested on 1,900 matches from " +
          "2018–23, their closing odds were more accurate than our model (log-loss 0.952 against 0.970; " +
          "lower is better), so this page leads with them and our model is a second opinion. Our model " +
          "rates teams from results and expected goals alone. This isn't betting advice."}
      </Explained>
      <div className="grid grid-cols-[1fr_auto_auto] rounded-2xl border border-[var(--line)] px-4 py-1.5 text-[14px] tabular-nums lg:max-w-[560px]">
        <span className="py-1.5 text-[12px] text-muted" />
        <span className="py-1.5 pl-4 text-right text-[12px] text-muted">Bookmakers</span>
        <span className="py-1.5 pl-4 text-right text-[12px] text-muted">Our model</span>
        {rows.map(([label, book, ours]) => (
          <div key={label} className="contents">
            <span className="border-t border-[var(--line)] py-1.5">{label}</span>
            <span className="border-t border-[var(--line)] py-1.5 pl-4 text-right font-semibold">{book}</span>
            <span className="border-t border-[var(--line)] py-1.5 pl-4 text-right">{ours}</span>
          </div>
        ))}
      </div>
    </section>
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
      <h3 className="text-[15px] font-semibold">Predicted lineups</h3>
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
        <h3 className="text-[15px] font-semibold">Best FPL picks from this match</h3>
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

// --- set-piece takers ------------------------------------------------------------------- //
const DUTIES = [
  ["penalties", "Penalties"],
  ["freekicks", "Direct free kicks"],
  ["corners", "Corners and indirect free kicks"],
] as const;
const OUT = new Set(["i", "s", "u", "n"]);

function SetPieceCard({ team, assets, xi, onOpen }: {
  team: string | null; assets: Prediction[]; xi: Set<number> | null; onOpen: (id: number) => void;
}) {
  const club = getClub(team);
  const mine = assets.filter((p) => p.team === team);
  return (
    <div className="flex min-w-0 flex-col gap-2 rounded-2xl border border-[var(--line)] px-4 py-3">
      <span className="flex min-w-0 items-center gap-2">
        <Jersey primary={club.primary} secondary={club.secondary} pattern={club.pattern} width={20} height={19} className="block flex-none" />
        <span className="truncate text-[14px] font-semibold">{team}</span>
      </span>
      {DUTIES.map(([duty, label]) => {
        const takers = mine
          .filter((p) => p.set_pieces[duty] != null)
          .sort((x, y) => (x.set_pieces[duty] ?? 99) - (y.set_pieces[duty] ?? 99))
          .slice(0, 3);
        const out = (p: Prediction) => OUT.has(p.availability.status ?? "");
        const playing = (p: Prediction) => !out(p) && (xi == null || xi.has(p.element_id));
        const likely = takers.find(playing);
        return (
          <div key={duty} className="flex flex-col gap-1 border-t border-[var(--line)] pt-2">
            <span className="text-[12px] text-muted">{label}</span>
            {takers.length === 0 ? (
              <span className="text-[13px] text-muted">None listed by FPL</span>
            ) : (
              <span className="flex flex-wrap gap-1.5">
                {takers.map((p) => {
                  const on = p === likely;
                  const note = on ? ", the likely taker" : out(p) ? ", out per FPL"
                    : !playing(p) ? ", not in our predicted eleven" : "";
                  return (
                    <button key={p.element_id} type="button" onClick={() => onOpen(p.element_id)}
                      title={`${p.web_name}: number ${p.set_pieces[duty]} on FPL's list${note}`}
                      className={`press rounded-full border px-2.5 py-0.5 text-[12px] font-semibold ${
                        on ? "border-emerald-600 bg-emerald-600 text-white"
                          : out(p) ? "border-[var(--line)] text-muted line-through"
                            : !playing(p) ? "border-[var(--line)] text-muted" : "border-[var(--line)] hover:border-emerald-600"}`}>
                      {`${p.set_pieces[duty]}. ${p.web_name}`}
                    </button>
                  );
                })}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

function SetPieces({ m, assets, onOpen }: { m: Match; assets: Prediction[]; onOpen: (id: number) => void }) {
  const lineups = [m.lineups?.home, m.lineups?.away];
  const xi = lineups.some(Boolean) ? new Set(lineups.flatMap((l) => l?.xi.map((p) => p.element_id) ?? [])) : null;
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-[15px] font-semibold">Set-piece takers</h3>
      <Explained label="Where does this come from?"
        head={<span className="text-[13px] text-muted">FPL&apos;s order of takers; the first one in our predicted eleven is marked.</span>}>
        {"FPL lists each club's order of takers for penalties, direct free kicks, and corners and indirect " +
          "free kicks. The highlighted player is the first on that list who is in our predicted eleven and " +
          "not ruled out by FPL. A struck-through name is injured or suspended; a faded one is fit but not in " +
          "our predicted eleven, and could still take one off the bench. Clubs change their takers without " +
          "notice, so this is FPL's latest list, not a certainty."}
      </Explained>
      <div className="grid gap-3 lg:grid-cols-2">
        <SetPieceCard team={m.home} assets={assets} xi={xi} onOpen={onOpen} />
        <SetPieceCard team={m.away} assets={assets} xi={xi} onOpen={onOpen} />
      </div>
    </section>
  );
}

function Scorelines({ m }: { m: Match }) {
  const rows = m.scorelines.slice(0, 6);
  const max = Math.max(...rows.map((r) => r.p), 0.0001);
  const h = getClub(m.home).shortCode, a = getClub(m.away).shortCode;
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-[15px] font-semibold">Likeliest scores</h3>
        <span className="text-[13px] text-muted">{`${h} – ${a}`}</span>
      </div>
      <ul className="flex flex-col gap-1.5 rounded-2xl border border-[var(--line)] px-4 py-3 lg:max-w-[560px]">
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
      <p className="text-[12px] text-muted">
        {`No single score is likely: these six cover ${pct(rows.reduce((s, r) => s + r.p, 0))} of outcomes between them. Both teams score ${pct(m.btts)}; over 2.5 goals ${pct(m.over_2_5)}.`}
      </p>
    </div>
  );
}

// --- the written read (only when a model wrote one and it passed the numeric guard) -------- //
const FACT_LABEL: Record<string, (m: Match) => string> = {
  home_win_pct: (m) => `${m.home} win`, away_win_pct: (m) => `${m.away} win`, draw_pct: () => "Draw",
  home_expected_goals: (m) => `${m.home} expected goals`, away_expected_goals: (m) => `${m.away} expected goals`,
  home_clean_sheet_pct: (m) => `${m.home} clean sheet`, away_clean_sheet_pct: (m) => `${m.away} clean sheet`,
  both_teams_to_score_pct: () => "Both score", over_2_5_goals_pct: () => "Over 2.5 goals",
  most_likely_score: () => "Likeliest score", most_likely_score_pct: () => "Likeliest score's chance",
  home_projected_formation: (m) => `${m.home} shape`, away_projected_formation: (m) => `${m.away} shape`,
};

function factChip(key: string, value: unknown, m: Match): string | null {
  const label = FACT_LABEL[key]?.(m);
  if (!label || value == null || typeof value === "object") return null;
  const v = typeof value === "number" ? (key.endsWith("_pct") ? `${value}%` : value.toFixed(1)) : String(value);
  return `${label}: ${v}`;
}

function TheRead({ m }: { m: Match }) {
  const b = m.brief;
  if (!b || b.generated_by === "template" || !b.angles?.length) return null;
  return (
    <div className="flex flex-col gap-2 rounded-2xl border border-[var(--line)] px-4 py-3">
      <h3 className="text-[15px] font-semibold">{b.headline}</h3>
      {b.angles.map((x, i) => (
        <div key={i} className="flex flex-col gap-1.5">
          <p className="text-[14px] leading-relaxed">{x.text}</p>
          <span className="flex flex-wrap gap-1">
            {x.evidence.map((k) => factChip(k, b.fact_pack?.[k], m)).filter(Boolean).map((t) => (
              <span key={t} className="rounded-full bg-[var(--chip)] px-2 py-0.5 text-[11px] tabular-nums text-muted">{t}</span>
            ))}
          </span>
        </div>
      ))}
      <p className="text-[12px] text-muted">Written by an AI model from the numbers on this page; every number in it was checked against them.</p>
    </div>
  );
}

// --- form ------------------------------------------------------------------------------ //
const RESULT_TONE = { W: "bg-emerald-600 text-white", D: "bg-[var(--chip)] text-[var(--fg)]", L: "bg-rose-600 text-white" } as const;

function FormRow({ team, games }: { team: string | null; games: FormResult[] }) {
  const club = getClub(team);
  const tally = (r: "W" | "D" | "L") => games.filter((g) => g.result === r).length;
  const gf = games.reduce((s, g) => s + g.gf, 0), ga = games.reduce((s, g) => s + g.ga, 0);
  return (
    <div className="flex flex-col gap-1.5">
      <span className="flex min-w-0 items-center gap-2">
        <Jersey primary={club.primary} secondary={club.secondary} pattern={club.pattern} width={18} height={17} className="block flex-none" />
        <span className="truncate text-[14px] font-semibold">{team}</span>
      </span>
      {games.length === 0 ? (
        <span className="text-[13px] text-muted">No results yet this season.</span>
      ) : (
        <>
          <span className="flex gap-1">
            {[...games].reverse().map((g) => (
              <span key={`${g.gw}-${g.opp_id}`} title={`GW${g.gw} ${g.home ? "v" : "at"} ${g.opp ?? "?"}: ${g.gf}–${g.ga}`}
                className={`grid h-7 w-7 place-items-center rounded-md text-[12px] font-bold ${RESULT_TONE[g.result]}`}>
                {g.result}
              </span>
            ))}
          </span>
          <span className="text-[12px] tabular-nums text-muted">
            {`${tally("W")}W ${tally("D")}D ${tally("L")}L · scored ${gf}, conceded ${ga} · oldest to newest`}
          </span>
        </>
      )}
    </div>
  );
}

function Form({ m }: { m: Match }) {
  if (!m.form) return null;
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-[15px] font-semibold">Form</h3>
      <div className="grid gap-3 rounded-2xl border border-[var(--line)] px-4 py-3 sm:grid-cols-2">
        <FormRow team={m.home} games={m.form.home} />
        <FormRow team={m.away} games={m.form.away} />
      </div>
    </div>
  );
}

// --- team news ----------------------------------------------------------------------------- //
function ago(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "Europe/London" }).format(d);
}

function ClubNews({ team, assets, news, onOpen }: {
  team: string | null; assets: Prediction[]; news: NewsResponse | null; onOpen: (id: number) => void;
}) {
  const club = getClub(team);
  const flagged = assets.filter((p) => p.team === team && isFlagged(p)).sort((a, b) => b.ownership - a.ownership);
  const stories = (team && news?.clubs?.[team]) || [];
  return (
    <div className="flex min-w-0 flex-col gap-2 rounded-2xl border border-[var(--line)] px-4 py-3">
      <span className="flex min-w-0 items-center gap-2">
        <Jersey primary={club.primary} secondary={club.secondary} pattern={club.pattern} width={20} height={19} className="block flex-none" />
        <span className="truncate text-[14px] font-semibold">{team}</span>
      </span>
      <div className="flex flex-col gap-1.5 border-t border-[var(--line)] pt-2">
        <span className="text-[12px] text-muted">Injured, suspended or doubtful, per FPL</span>
        {flagged.length === 0 ? (
          <span className="text-[13px] text-muted">Nobody flagged.</span>
        ) : flagged.map((p) => {
          const a = p.availability;
          const tag = a.chance != null && a.chance > 0 ? `${a.chance}%` : (a.label ?? "Out");
          return (
            <button key={p.element_id} type="button" onClick={() => onOpen(p.element_id)}
              className="press flex items-start gap-2 text-left text-inherit">
              <span className={`mt-0.5 flex-none rounded px-[5px] text-[11px] font-bold ${a.chance != null && a.chance > 0 ? "bg-amber-100 text-amber-900" : "bg-rose-100 text-rose-900"}`}>{tag}</span>
              <span className="min-w-0 text-[13px]">
                <span className="font-semibold">{p.web_name}</span>
                {a.news ? <span className="text-muted">{` · ${a.news}`}</span> : null}
              </span>
            </button>
          );
        })}
      </div>
      <div className="flex flex-col gap-1.5 border-t border-[var(--line)] pt-2">
        <span className="text-[12px] text-muted">This week&apos;s stories</span>
        {stories.length === 0 ? (
          <span className="text-[13px] text-muted">No team news stories this week.</span>
        ) : stories.slice(0, 3).map((n, i) => (
          <a key={n.link ?? i} href={n.link ?? undefined} target="_blank" rel="noopener noreferrer"
            className="press flex flex-col text-[13px] text-inherit hover:text-[var(--emerald-text)]">
            <span className="font-semibold">{n.title}</span>
            <span className="text-[12px] text-muted">{[n.labels?.join(", "), ago(n.published)].filter(Boolean).join(" · ")}</span>
          </a>
        ))}
      </div>
    </div>
  );
}

function TeamNews({ m, assets, news, onOpen }: { m: Match; assets: Prediction[]; news: NewsResponse | null; onOpen: (id: number) => void }) {
  return (
    <div className="flex flex-col gap-2">
      <Explained label="Where does this come from?"
        head={<span className="text-[13px] text-muted">FPL&apos;s own flags first, then the week&apos;s team news.</span>}>
        {"Flags are FPL's own injury and suspension statuses, as our projections used them; a percentage is " +
          "FPL's chance of playing. The stories are the week's team news about each club from the sources the " +
          "News page reads, filtered to first-team injuries, suspensions, returns and line-ups."}
      </Explained>
      <div className="grid gap-3 lg:grid-cols-2">
        <ClubNews team={m.home} assets={assets} news={news} onOpen={onOpen} />
        <ClubNews team={m.away} assets={assets} news={news} onOpen={onOpen} />
      </div>
    </div>
  );
}

// --- FPL angles -------------------------------------------------------------------------- //
type Angle = "score" | "assist" | "cs";
const ANGLES = [["score", "To score"], ["assist", "To assist"], ["cs", "Clean sheet"]] as const;

function chanceOf(p: Prediction, angle: Angle): number | null {
  const b = p.breakdown;
  if (!b) return null;
  if (angle === "score") return atLeastOne(b.x_goals);
  if (angle === "assist") return atLeastOne(b.x_assists);
  return p.position === "GK" || p.position === "DEF" ? b.p_clean_sheet * b.p_60 : null;
}

function Callout({ label, p, sub, onOpen }: { label: string; p: Prediction; sub: string; onOpen: (id: number) => void }) {
  const club = getClub(p.team);
  return (
    <button type="button" onClick={() => onOpen(p.element_id)}
      className="press flex min-w-0 items-center gap-2.5 rounded-2xl border border-[var(--line)] px-3 py-2.5 text-left text-inherit hover:border-emerald-600">
      <Jersey primary={club.primary} secondary={club.secondary} pattern={club.pattern} width={24} height={23} className="block flex-none" />
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="text-[12px] text-muted">{label}</span>
        <span className="truncate text-[15px] font-semibold">{p.web_name}</span>
        <span className="text-[12px] tabular-nums text-muted">{sub}</span>
      </span>
    </button>
  );
}

function Highlights({ assets, onOpen }: { assets: Prediction[]; onOpen: (id: number) => void }) {
  const captain = assets[0];
  const diff = assets.find((p) => p.ownership < DIFFERENTIAL_OWNERSHIP);
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {captain && <Callout label="Captain pick from this match" p={captain} sub={`${captain.xp.toFixed(1)} expected points · ${captain.ownership.toFixed(1)}% owned`} onOpen={onOpen} />}
      {diff && <Callout label={`Differential (under ${DIFFERENTIAL_OWNERSHIP}% owned)`} p={diff} sub={`${diff.xp.toFixed(1)} expected points · ${diff.ownership.toFixed(1)}% owned`} onOpen={onOpen} />}
    </div>
  );
}

function Chances({ assets, onOpen }: { assets: Prediction[]; onOpen: (id: number) => void }) {
  const [angle, setAngle] = useState<Angle>("score");
  const ranked = assets
    .map((p) => ({ p, c: chanceOf(p, angle) }))
    .filter((x): x is { p: Prediction; c: number } => x.c != null && x.c > 0.005)
    .sort((a, b) => b.c - a.c)
    .slice(0, 8);
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-[15px] font-semibold">Each player&apos;s chances</h3>
          <Segmented label="Which chance" options={ANGLES} value={angle} onChange={setAngle} />
        </div>
        <ul className="flex flex-col rounded-2xl border border-[var(--line)] px-4">
          {ranked.map(({ p, c }) => {
            const club = getClub(p.team);
            return (
              <li key={p.element_id} className="border-t border-[var(--line)] first:border-t-0">
                <button type="button" onClick={() => onOpen(p.element_id)}
                  className="press flex w-full items-center gap-2.5 py-2 text-left text-inherit">
                  <Jersey primary={club.primary} secondary={club.secondary} pattern={club.pattern} width={20} height={19} className="block flex-none" />
                  <span className="min-w-0 flex-1 truncate text-[14px] font-semibold">{p.web_name}</span>
                  <span className="text-[12px] text-muted">{`${club.shortCode} · ${p.position}`}</span>
                  <span className="t-title w-12 flex-none text-right text-[15px] font-bold tabular-nums">{pct(c)}</span>
                </button>
              </li>
            );
          })}
        </ul>
        <p className="text-[12px] text-muted">
          {angle === "cs"
            ? "Chance of a clean sheet while playing 60 minutes or more, which is what FPL pays, for keepers and defenders."
            : `Chance of at least one ${angle === "score" ? "goal" : "assist"}, from our model's expected ${angle === "score" ? "goals" : "assists"} for him in this match, which already allow for the chance he doesn't play.`}
        </p>
      </div>
    </div>
  );
}

// --- the section strip ------------------------------------------------------------------- //
type SectionKey = "overview" | "news" | "lineups" | "fpl" | "scores";
const SECTION_LABEL: Record<SectionKey, string> = { overview: "Overview", news: "News", lineups: "Lineups", fpl: "FPL", scores: "Scores" };

function SectionStrip({ keys }: { keys: SectionKey[] }) {
  return (
    <nav aria-label="Sections" className="chrome-strong sticky top-[var(--nav-h)] z-20 -mx-4 border-b border-[var(--line)] px-4">
      <ul className="flex gap-1 overflow-x-auto py-2 [scrollbar-width:none]">
        {keys.map((k) => (
          <li key={k} className="flex-none">
            <a href={`#${k}`} className="press block rounded-full px-3 py-1.5 text-[13px] font-semibold text-muted hover:bg-[var(--chip)] hover:text-[var(--fg)]">
              {SECTION_LABEL[k]}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function Section({ id, title, children }: { id: SectionKey; title: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-h`} className="flex scroll-mt-[calc(var(--nav-h)+56px)] flex-col gap-4">
      <h2 id={`${id}-h`} className="t-title text-[19px] font-bold">{title}</h2>
      {children}
    </section>
  );
}

// --- the page's one client component -------------------------------------------------- //
export function MatchLab({ match, assets, gw, news }: {
  match: Match; assets: Prediction[]; gw: number; news: NewsResponse | null;
}) {
  const [openId, setOpenId] = useState<number | null>(null);
  const byId = useMemo(() => new Map(assets.map((p) => [p.element_id, p])), [assets]);
  const open = openId != null ? byId.get(openId) : undefined;
  const onOpen = (id: number) => { if (byId.has(id)) setOpenId(id); };
  // Lineups, team news and picks exist only for the gameweek being projected.
  const thisWeek = match.gw === gw && assets.length > 0;
  const keys: SectionKey[] = thisWeek ? ["overview", "news", "lineups", "fpl", "scores"] : ["overview", "scores"];

  return (
    <div className="flex flex-col gap-8">
      <SectionStrip keys={keys} />
      <Section id="overview" title="Overview">
        <div className="flex flex-col gap-3">
          <ResultBar m={match} />
          <OddsTiles m={match} />
        </div>
        <TheRead m={match} />
        <SecondOpinion m={match} />
        <Form m={match} />
      </Section>
      {thisWeek ? (
        <>
          <Section id="news" title="Team news">
            <TeamNews m={match} assets={assets} news={news} onOpen={onOpen} />
          </Section>
          <Section id="lineups" title="Lineups">
            <Lineups m={match} onOpen={onOpen} />
            <SetPieces m={match} assets={assets} onOpen={onOpen} />
          </Section>
          <Section id="fpl" title="FPL">
            <Highlights assets={assets} onOpen={onOpen} />
            <Picks assets={assets} onOpen={onOpen} />
            <Chances assets={assets} onOpen={onOpen} />
          </Section>
        </>
      ) : (
        <p className="rounded-2xl border border-[var(--line)] p-4 text-[14px] text-muted">
          {`Team news, predicted lineups and the FPL picks appear in gameweek ${match.gw}, once it's the next one.`}
        </p>
      )}
      <Section id="scores" title="Scores">
        <Scorelines m={match} />
      </Section>
      {open && <PlayerSheet player={open} gw={gw} onClose={() => setOpenId(null)} />}
    </div>
  );
}
