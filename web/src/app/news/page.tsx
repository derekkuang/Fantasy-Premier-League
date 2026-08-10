// Team news — BETA, and it says so at the top rather than in a footnote.
//
// This page exists because of a measurement, not a hunch: perfect team news is worth roughly
// fourteen times more to the model than the best modelling change we found (docs/HANDOFF.md §19).
// FPL's own availability field covers the INJURY half for free and in detail. It says almost
// nothing about ROTATION, and rotation is what a manager's press conference is actually about.
//
// So the page has one rule, and it is the same rule as /model: never claim more than was
// measured. Every headline here is a link to its publisher, every keyword tag is labelled as
// routing rather than judgement, and FPL's own status is printed beside every player so the
// reader can see both sources instead of being told which to believe. Nothing on this page
// changes a single projection anywhere else on the site.

import type { Metadata } from "next";
import Link from "next/link";
import { getNews, type NewsItem, type NewsResponse } from "@/lib/api";
import { PageError, PageShell } from "@/components/page-shell";

export const metadata: Metadata = {
  title: "Team news (beta) — FPL Edge",
  description:
    "Automated team-news digest from public club feeds, shown beside FPL's own availability status. Beta: keyword routing, not classification, and it changes no projection.",
  alternates: { canonical: "/news" },
};

export const revalidate = 900;

const CUE_LABEL: Record<string, string> = {
  injury: "injury",
  return: "return",
  rotation: "rotation",
  suspension: "suspension",
};

// FPL's own codes. Shown verbatim beside anything we surface, because on availability FPL is
// the authority and we are a second opinion.
const STATUS_LABEL: Record<string, string> = {
  a: "available",
  d: "doubtful",
  i: "injured",
  s: "suspended",
  u: "unavailable",
};

function Cue({ tag }: { tag: string }) {
  const tone =
    tag === "injury" || tag === "suspension"
      ? "bg-red-500/10 text-red-700 dark:text-red-400"
      : tag === "rotation"
        ? "bg-amber-500/10 text-amber-700 dark:text-amber-400"
        : "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400";
  return (
    <span className={`t-label rounded-full px-2 py-0.5 text-[10px] font-medium ${tone}`}>
      {CUE_LABEL[tag] ?? tag}
    </span>
  );
}

function Item({ item }: { item: NewsItem }) {
  return (
    <li className="border-t border-black/5 py-3 first:border-t-0 dark:border-white/10">
      <div className="flex flex-wrap items-start gap-x-2 gap-y-1">
        {item.link ? (
          <a
            href={item.link}
            target="_blank"
            rel="noopener noreferrer"
            className="press text-[13px] font-medium leading-snug hover:text-emerald-600"
          >
            {item.title}
          </a>
        ) : (
          <span className="text-[13px] font-medium leading-snug">{item.title}</span>
        )}
        {item.cues.map((c) => (
          <Cue key={c} tag={c} />
        ))}
      </div>
      {item.summary ? (
        <p className="mt-1 text-[12px] leading-snug text-black/55 dark:text-white/55">
          {item.summary}
        </p>
      ) : null}
      {item.mentions.length > 0 ? (
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {item.mentions.map((m) => (
            <span
              key={m.element_id}
              className="t-label rounded-md bg-black/[0.04] px-2 py-0.5 text-[11px] dark:bg-white/[0.06]"
            >
              {m.name}
              {/* FPL's own line wins the last word on availability, always. */}
              {m.fpl_news ? (
                <span className="ml-1 text-black/45 dark:text-white/45">
                  · FPL: {m.fpl_news}
                </span>
              ) : m.fpl_status && m.fpl_status !== "a" ? (
                <span className="ml-1 text-black/45 dark:text-white/45">
                  · FPL: {STATUS_LABEL[m.fpl_status] ?? m.fpl_status}
                </span>
              ) : null}
            </span>
          ))}
        </div>
      ) : null}
    </li>
  );
}

export default async function NewsPage() {
  let data: NewsResponse;
  try {
    data = await getNews();
  } catch (e) {
    // PageError renders its own shell. Not wrapped in a second one.
    return (
      <PageError
        message={
          e instanceof Error
            ? `${e.message} This page fills in once the daily capture has run.`
            : "Could not load team news."
        }
      />
    );
  }

  const clubs = Object.entries(data.clubs);
  const generated = new Date(data.generated_at);

  return (
    <PageShell title="Team news">
      <div className="mb-4 rounded-xl border border-amber-500/25 bg-amber-500/[0.06] p-3">
        <div className="flex items-center gap-2">
          <span className="t-label rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] font-semibold text-amber-800 dark:text-amber-300">
            BETA
          </span>
          <span className="t-label text-[11px] text-black/55 dark:text-white/55">
            updated {generated.toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" })}
          </span>
        </div>
        <p className="mt-2 text-[12px] leading-relaxed text-black/70 dark:text-white/70">
          {data.disclaimer}
        </p>
      </div>

      {/* The page grades itself. Publishing precision and recall beside the content is the
          same discipline as /model — a feature that cannot be checked should not be trusted. */}
      <div className="mb-5 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {[
          ["items tracked", String(data.n_items)],
          ["clubs", `${data.n_clubs}/20`],
          [
            "agrees with FPL",
            data.quality.precision === null ? "—" : `${Math.round(data.quality.precision * 100)}%`,
          ],
          ["rotation hints", String(data.quality.additive)],
        ].map(([label, value]) => (
          <div
            key={label}
            className="rounded-lg border border-black/5 bg-black/[0.02] p-2.5 dark:border-white/10 dark:bg-white/[0.03]"
          >
            <div className="t-label text-[10px] uppercase text-black/45 dark:text-white/45">
              {label}
            </div>
            <div className="mt-0.5 text-lg font-semibold tabular-nums">{value}</div>
          </div>
        ))}
      </div>

      <p className="mb-5 text-[12px] leading-relaxed text-black/55 dark:text-white/55">
        Headlines come from public club feeds. The coloured tags are <em>keyword routing</em>, not
        judgements — they say a phrase appeared, not that a manager meant it. Where FPL has
        published a status for a player it is printed beside them and is the authority.{" "}
        <Link href="/model" className="press underline decoration-black/20 hover:text-emerald-600">
          How we measure things
        </Link>
        .
      </p>

      {clubs.length === 0 ? (
        <p className="text-sm text-black/55 dark:text-white/55">
          Nothing captured yet. This fills in once the daily capture has run.
        </p>
      ) : (
        <div className="space-y-5">
          {clubs.map(([club, items]) => (
            <section key={club}>
              <h2 className="t-title mb-1 text-[13px] font-semibold">{club}</h2>
              <ul className="rounded-xl border border-black/5 px-3 dark:border-white/10">
                {items.map((it, i) => (
                  <Item key={`${club}-${i}`} item={it} />
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </PageShell>
  );
}
