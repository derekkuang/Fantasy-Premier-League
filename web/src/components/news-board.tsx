"use client";
// The team-news list: one row per club, closed until tapped, with how many stories it holds.
// If you've built a squad on this site, one switch narrows the page to stories about your
// players. Keyword tags ("injury", "rotation") are gone: they agreed with FPL about a quarter
// of the time, so they mislabelled more than they helped. FPL's own status stays beside each
// player, because on availability FPL is the authority.

import { useMemo, useState, useSyncExternalStore } from "react";
import type { NewsItem, NewsSource } from "@/lib/api";

const SOURCE: Record<NewsSource, string> = { official: "Club", pl: "Premier League", bbc: "BBC", guardian: "Guardian" };
const STATUS: Record<string, string> = { d: "doubtful", i: "injured", s: "suspended", u: "unavailable", n: "unavailable" };

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

function Story({ item, mine }: { item: NewsItem; mine: Set<number> }) {
  const sources = item.sources?.length ? item.sources : item.source ? [item.source] : [];
  return (
    <li className="flex flex-col gap-1 border-t border-[var(--line)] py-3 first:border-t-0">
      {item.link ? (
        <a href={item.link} target="_blank" rel="noopener noreferrer" className="press text-[14px] font-semibold leading-snug hover:text-[var(--emerald-text)]">
          {item.title}
        </a>
      ) : (
        <span className="text-[14px] font-semibold leading-snug">{item.title}</span>
      )}
      {item.summary && <p className="line-clamp-2 text-[13px] leading-snug text-muted">{item.summary}</p>}
      <div className="flex flex-wrap items-center gap-1.5">
        {sources.map((s) => (
          <span key={s} className="text-[12px] text-muted">{SOURCE[s] ?? s}</span>
        ))}
        {item.mentions.map((m) => {
          const flagged = m.fpl_status && m.fpl_status !== "a";
          return (
            <span
              key={m.element_id}
              className={`rounded-md px-2 py-0.5 text-[12px] ${
                flagged ? "bg-[var(--amber-bg)] text-[var(--amber-fg)]" : "bg-black/[.04] dark:bg-white/[.07]"
              } ${mine.has(m.element_id) ? "font-semibold" : ""}`}
            >
              {m.name}
              {m.fpl_news ? ` · FPL: ${m.fpl_news}` : flagged ? ` · FPL: ${STATUS[m.fpl_status!] ?? m.fpl_status}` : ""}
            </span>
          );
        })}
      </div>
    </li>
  );
}

export function NewsBoard({ clubs }: { clubs: [string, NewsItem[]][] }) {
  const squad = useSavedSquad();
  const mine = useMemo(() => new Set(squad), [squad]);
  const [onlyMine, setOnlyMine] = useState(false);

  const shown = clubs
    .map(([club, items]) => [club, onlyMine ? items.filter((i) => i.mentions.some((m) => mine.has(m.element_id))) : items] as const)
    .filter(([, items]) => items.length > 0);

  return (
    <div className="flex flex-col gap-3">
      {mine.size > 0 && (
        <label className="flex min-h-11 w-fit cursor-pointer items-center gap-2.5 text-[14px]">
          <input type="checkbox" checked={onlyMine} onChange={(e) => setOnlyMine(e.target.checked)} className="h-5 w-5 accent-emerald-600" />
          Only stories about players in my squad
        </label>
      )}

      {shown.length === 0 ? (
        <p className="text-[14px] text-muted">
          {onlyMine ? "Nothing about your players right now." : "No team news has been collected yet."}
        </p>
      ) : (
        <div className="flex flex-col rounded-2xl border border-[var(--line)] px-4">
          {shown.map(([club, items], i) => {
            const flagged = items.reduce((n, it) => n + it.mentions.filter((m) => m.fpl_status && m.fpl_status !== "a").length, 0);
            return (
              <details key={club} className={`fold ${i ? "border-t border-[var(--line)]" : ""}`} open={onlyMine}>
                <summary className="press flex min-h-12 cursor-pointer items-center justify-between gap-3 py-2">
                  <span className="text-[15px] font-semibold">{club}</span>
                  <span className="flex items-center gap-2 text-[13px] text-muted">
                    {flagged > 0 && (
                      <span className="rounded-full bg-[var(--amber-bg)] px-2 py-0.5 text-[12px] font-semibold text-[var(--amber-fg)]">
                        {flagged} flagged by FPL
                      </span>
                    )}
                    <span className="tabular-nums">{items.length} {items.length === 1 ? "story" : "stories"}</span>
                    <svg aria-hidden className="chev flex-none" width="8" height="12" viewBox="0 0 8 12">
                      <path d="M1.5 1.5 6 6l-4.5 4.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </span>
                </summary>
                <ul className="pb-1">
                  {items.map((it, j) => <Story key={`${club}-${j}`} item={it} mine={mine} />)}
                </ul>
              </details>
            );
          })}
        </div>
      )}
    </div>
  );
}
