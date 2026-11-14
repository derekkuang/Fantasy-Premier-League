"use client";
// Team news, availability first (HANDOFF §39).
//
// 1. Injuries and suspensions: everyone FPL itself marks doubtful, injured or suspended,
//    most-owned first, in FPL's own words, with any story we have about them underneath.
//    Complete even when no feed has written about a player, because it comes from FPL.
// 2. Latest team news: stories from the last week whose headline is an injury, suspension,
//    return, line-up, press conference or manager change at a first team. The filtering is
//    done when the digest is built (fpledge/news_filter.py); this only lays it out.
//
// With a squad saved in the builder, one switch narrows both to your players.

import { useMemo, useState, useSyncExternalStore } from "react";
import type { FlaggedPlayer, NewsItem, NewsMention, NewsSource } from "@/lib/api";
import { getClub } from "@/lib/clubs";
import { Jersey } from "@/components/jersey";
import { Segmented } from "@/components/segmented";

export type Story = NewsItem & { club: string };

const SOURCE: Record<NewsSource, string> = { official: "Club site", pl: "Premier League", bbc: "BBC", guardian: "Guardian" };
const LABEL_TONE: Record<string, string> = {
  Injury: "bg-[var(--amber-bg)] text-[var(--amber-fg)]",
  Suspension: "bg-rose-500/10 text-[var(--rose)]",
  Return: "bg-emerald-500/12 text-[var(--emerald-text)]",
};
const FIRST_FLAGGED = 8;   // the most-owned first; the rest one tap away
const FIRST_STORIES = 10;

/** The squad saved by the squad builder (element ids), read the way React wants local storage read. */
function useSavedSquad(): number[] {
  const raw = useSyncExternalStore(
    (on) => { window.addEventListener("storage", on); return () => window.removeEventListener("storage", on); },
    () => { try { return localStorage.getItem("fpledge.squad") ?? "[]"; } catch { return "[]"; } },
    () => "[]",
  );
  return useMemo(() => {
    try { const v = JSON.parse(raw); return Array.isArray(v) ? (v as number[]) : []; } catch { return []; }
  }, [raw]);
}

/** "today", "yesterday", "3 days ago", relative to when the digest was built so the page reads
 *  the same for everyone who opens it. */
function ago(when: string | null, now: number): string {
  if (!when) return "";
  const t = Date.parse(when);
  if (Number.isNaN(t)) return "";
  const days = Math.floor((now - t) / 86_400_000);
  return days <= 0 ? "today" : days === 1 ? "yesterday" : `${days} days ago`;
}

function StatusChip({ p }: { p: FlaggedPlayer }) {
  const [text, tone] =
    p.status === "s" ? ["Suspended", "bg-rose-500/10 text-[var(--rose)]"]
    : p.status === "i" || p.chance === 0 ? ["Out", "bg-rose-500/10 text-[var(--rose)]"]
    : [`${p.chance ?? "?"}%`, "bg-[var(--amber-bg)] text-[var(--amber-fg)]"];
  return (
    <span title={p.status === "d" ? `${p.chance}% chance of playing, per FPL` : undefined}
      className={`flex-none rounded-full px-2.5 py-0.5 text-[12px] font-semibold tabular-nums ${tone}`}>
      {text}
    </span>
  );
}

function StoryLink({ s }: { s: Story }) {
  return s.link ? (
    <a href={s.link} target="_blank" rel="noopener noreferrer" className="press hover:text-[var(--emerald-text)]">{s.title}</a>
  ) : <span>{s.title}</span>;
}

function sourcesOf(s: Story): string {
  const list = s.sources?.length ? s.sources : s.source ? [s.source] : [];
  return list.map((x) => SOURCE[x] ?? x).join(", ");
}

function FlaggedRow({ p, stories, now }: { p: FlaggedPlayer; stories: Story[]; now: number }) {
  const club = getClub(p.team);
  const story = stories[0];
  return (
    <li className="flex flex-col gap-1 border-t border-[var(--line)] py-3 first:border-t-0">
      <div className="flex items-center gap-2.5">
        <Jersey primary={club.primary} secondary={club.secondary} pattern={club.pattern} width={22} height={21} className="block flex-none" />
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="truncate text-[14px] font-semibold">{p.name}</span>
          <span className="text-[12px] tabular-nums text-muted">
            {club.shortCode} · {p.position} · {p.ownership.toFixed(1)}% owned
          </span>
        </span>
        <StatusChip p={p} />
      </div>
      <p className="pl-[34px] text-[13px] leading-snug">
        {p.news || "No detail from FPL."}
        {p.news_added && <span className="text-muted">{` · ${ago(p.news_added, now)}`}</span>}
      </p>
      {story && (
        <p className="pl-[34px] text-[12px] leading-snug text-muted">
          <StoryLink s={story} />
          {` · ${sourcesOf(story)}`}
        </p>
      )}
    </li>
  );
}

function PlayerChip({ m }: { m: NewsMention }) {
  const flagged = m.fpl_status && m.fpl_status !== "a";
  return (
    <span className={`rounded-md px-2 py-0.5 text-[12px] ${flagged ? "bg-[var(--amber-bg)] text-[var(--amber-fg)]" : "bg-[var(--chip)]"}`}>
      {m.name}
      {flagged && m.fpl_news ? ` · FPL: ${m.fpl_news}` : ""}
    </span>
  );
}

function StoryRow({ s, now }: { s: Story; now: number }) {
  return (
    <li className="flex flex-col gap-1.5 border-t border-[var(--line)] py-3 first:border-t-0">
      <div className="flex flex-wrap items-center gap-1.5 text-[12px] text-muted">
        {(s.labels ?? []).map((l) => (
          <span key={l} className={`rounded-full px-2 py-0.5 font-semibold ${LABEL_TONE[l] ?? "bg-[var(--chip)] text-[var(--fg)]"}`}>{l}</span>
        ))}
        <span>{s.club}</span>
        {s.published && <span>{`· ${ago(s.published, now)}`}</span>}
      </div>
      <span className="text-[14px] font-semibold leading-snug"><StoryLink s={s} /></span>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[12px] text-muted">{sourcesOf(s)}</span>
        {(s.players ?? []).map((m) => <PlayerChip key={m.element_id} m={m} />)}
      </div>
    </li>
  );
}

export function NewsBoard({ flagged, stories, generatedAt, windowDays }: {
  flagged: FlaggedPlayer[];
  stories: Story[];
  generatedAt: string;
  windowDays: number;
}) {
  const squad = useSavedSquad();
  const mine = useMemo(() => new Set(squad), [squad]);
  const [scope, setScope] = useState<"all" | "mine">("all");
  const [showAll, setShowAll] = useState(false);
  const [allStories, setAllStories] = useState(false);
  const now = Date.parse(generatedAt) || 0;

  const onlyMine = scope === "mine" && mine.size > 0;
  const flaggedShown = onlyMine ? flagged.filter((p) => mine.has(p.element_id)) : flagged;
  const storiesShown = onlyMine ? stories.filter((s) => (s.players ?? []).some((m) => mine.has(m.element_id))) : stories;
  const storiesFor = useMemo(() => {
    const out = new Map<number, Story[]>();
    for (const s of stories) for (const m of s.players ?? []) out.set(m.element_id, [...(out.get(m.element_id) ?? []), s]);
    return out;
  }, [stories]);
  const visible = showAll || onlyMine ? flaggedShown : flaggedShown.slice(0, FIRST_FLAGGED);

  return (
    <div className="flex flex-col gap-6">
      {mine.size > 0 && (
        <Segmented label="Whose news" className="self-start"
          options={[["all", "All players"], ["mine", "My squad"]] as const} value={scope} onChange={setScope} />
      )}

      <section className="flex flex-col gap-2">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="t-title text-[17px] font-semibold">Injuries and suspensions</h2>
          <span className="text-[13px] tabular-nums text-muted">{flaggedShown.length} flagged by FPL</span>
        </div>
        {flaggedShown.length === 0 ? (
          <p className="text-[14px] text-muted">{onlyMine ? "None of your players is flagged." : "FPL hasn't flagged anyone."}</p>
        ) : (
          <>
            <ul className="flex flex-col rounded-2xl border border-[var(--line)] px-4">
              {visible.map((p) => <FlaggedRow key={p.element_id} p={p} stories={storiesFor.get(p.element_id) ?? []} now={now} />)}
            </ul>
            {visible.length < flaggedShown.length && (
              <button type="button" onClick={() => setShowAll(true)}
                className="press self-center rounded-full border border-[var(--line)] px-4 py-2 text-[13px] font-semibold hover:border-emerald-600">
                {`Show all ${flaggedShown.length}`}
              </button>
            )}
          </>
        )}
      </section>

      <section className="flex flex-col gap-2">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="t-title text-[17px] font-semibold">Latest team news</h2>
          <span className="text-[13px] tabular-nums text-muted">{`last ${windowDays} days`}</span>
        </div>
        {storiesShown.length === 0 ? (
          <p className="text-[14px] text-muted">{onlyMine ? "Nothing about your players this week." : "No team news this week yet."}</p>
        ) : (
          <>
            <ul className="flex flex-col rounded-2xl border border-[var(--line)] px-4">
              {(allStories || onlyMine ? storiesShown : storiesShown.slice(0, FIRST_STORIES)).map((s, i) => (
                <StoryRow key={`${s.club}-${i}`} s={s} now={now} />
              ))}
            </ul>
            {!allStories && !onlyMine && storiesShown.length > FIRST_STORIES && (
              <button type="button" onClick={() => setAllStories(true)}
                className="press self-center rounded-full border border-[var(--line)] px-4 py-2 text-[13px] font-semibold hover:border-emerald-600">
                {`Show all ${storiesShown.length}`}
              </button>
            )}
          </>
        )}
      </section>
    </div>
  );
}
