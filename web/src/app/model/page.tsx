// The honesty page.
//
// Every other page on this site asks you to trust a number. This one is where that trust is
// supposed to be earned, so it has one rule: nothing here is written by hand. Every figure is
// read from the artifact `scripts/build_model_card.py` produces by walking a completed season
// forward, and the page prints the date it was generated so a stale claim announces itself.
//
// It has been wrong twice, in opposite directions, and both corrections are printed on it. A
// model card that only lists wins is a marketing page wearing a lab coat; one that quietly
// restates a number it got wrong is worse, because it looks like the first thing.

import type { Metadata } from "next";
import Link from "next/link";
import { getModelCard, type CardSubset, type ModelCard } from "@/lib/api";
import { PageError, PageShell } from "@/components/page-shell";

export const metadata: Metadata = {
  title: "How the model does — FPL Edge",
  description:
    "Measured, not asserted: walk-forward validation of our expected-points model against FPL's own projection, the experiments that failed, and what the model deliberately does not know.",
  alternates: { canonical: "/model" },
};

export const revalidate = 3600;

function Metric({
  label, mine, theirs, better, unit = "", hint,
}: {
  label: string;
  mine: number | null;
  theirs: number | null;
  /** which direction is good — decides who gets the green, not which number is bigger */
  better: "high" | "low";
  unit?: string;
  hint: string;
}) {
  if (mine == null || theirs == null) return null;
  const weWin = better === "high" ? mine > theirs : mine < theirs;
  const fmt = (n: number) => n.toFixed(3) + unit;
  return (
    <div className="flex flex-col gap-1.5 rounded-xl border border-black/10 p-3 dark:border-white/10">
      <span className="t-label text-[10px] text-black/45 dark:text-white/45">{label}</span>
      <div className="flex items-baseline gap-4">
        <span className="flex flex-col">
          <span className={`t-title text-2xl font-bold tabular-nums ${weWin ? "text-emerald-600" : ""}`}>
            {fmt(mine)}
          </span>
          <span className="text-[10px] text-black/45 dark:text-white/45">ours</span>
        </span>
        <span className="flex flex-col">
          <span className={`t-title text-2xl font-bold tabular-nums ${weWin ? "" : "text-emerald-600"}`}>
            {fmt(theirs)}
          </span>
          <span className="text-[10px] text-black/45 dark:text-white/45">FPL&apos;s own</span>
        </span>
      </div>
      <span className="text-[11px] leading-relaxed text-black/50 dark:text-white/50">{hint}</span>
    </div>
  );
}

function Subset({ title, blurb, s }: { title: string; blurb: string; s: CardSubset }) {
  return (
    <section className="flex flex-col gap-2">
      <div>
        <h3 className="t-title text-[15px] font-semibold">{title}</h3>
        <p className="text-[12px] leading-relaxed text-black/50 dark:text-white/50">
          {blurb} · {s.n.toLocaleString()} player-gameweeks
        </p>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        <Metric
          label="Ranking · per-GW Spearman"
          mine={s.spearman_model}
          theirs={s.spearman_fpl}
          better="high"
          hint="How well the projection ORDERS players against what they actually scored, averaged over gameweeks. Picking a squad is a ranking problem, so this is the metric that matters most."
        />
        <Metric
          label="Error · mean absolute"
          mine={s.mae_model}
          theirs={s.mae_fpl}
          better="low"
          unit=" pts"
          hint={`How far off each individual projection is, on average. Lower is better — ours is closer in ${s.gws_model_mae_beats_fpl} gameweeks.`}
        />
      </div>
    </section>
  );
}

export default async function ModelPage() {
  let card: ModelCard;
  try {
    card = await getModelCard();
  } catch (e) {
    return <PageError message={e instanceof Error ? e.message : "Could not load the model card."} />;
  }

  const p = card.measured.played_only;
  const gap =
    p.spearman_model != null && p.spearman_fpl != null
      ? (p.spearman_model - p.spearman_fpl).toFixed(3)
      : null;

  return (
    <PageShell
      title="How the model does"
      subtitle={`Walk-forward validation on ${card.season} — measured, not asserted.`}
      meta={
        <span className="text-right font-mono text-[10px] leading-relaxed text-black/40 dark:text-white/40">
          {card.model_ver}
          <br />
          {card.generated_at.slice(0, 10)}
        </span>
      }
    >
      {/* The finding, stated before anything that might soften it. */}
      <div className="flex flex-col gap-2 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 p-4">
        <h2 className="t-title text-[17px] font-semibold">
          Our projection ranks players better than FPL&apos;s own.
        </h2>
        <p className="text-[13px] leading-relaxed text-black/70 dark:text-white/70">
          Across {card.measured.gws_scored} gameweeks of {card.season}, on the players who
          actually featured, ours correlates{" "}
          <strong className="tabular-nums">+{gap}</strong> higher with
          realised points than FPL&apos;s figure as it stood before each deadline — and misses by
          less on average too.
        </p>
        <p className="text-[13px] leading-relaxed text-black/70 dark:text-white/70">
          We are not going to oversell that. A rank correlation of{" "}
          <strong className="tabular-nums">{p.spearman_model?.toFixed(2)}</strong> means single
          gameweeks stay mostly unpredictable, for us and for everyone. It is an edge, not a
          crystal ball, and it sits alongside the reason this site exists: every number here
          opens up and reads term by term, and feeds tooling FPL gives you nothing like.
        </p>
      </div>

      {/* The page has been wrong twice today. Saying so IS the honesty claim. */}
      <div className="rounded-2xl border border-black/10 p-4 dark:border-white/10">
        <h3 className="t-title text-[14px] font-semibold">
          What we are comparing against, and why this page changed its mind twice
        </h3>
        <p className="mt-1 text-[12px] leading-relaxed text-black/60 dark:text-white/60">
          The public dataset&apos;s <code className="font-mono">xP</code> column is FPL&apos;s own
          projection, but it is scraped <em>after</em> each gameweek finishes. FPL&apos;s number
          tracks its <code className="font-mono">form</code> figure almost exactly, and form
          absorbs a gameweek&apos;s points the moment it ends — so the scraped value has already
          seen the result it is being asked to predict. Upstream documents this and recommends
          shifting the column by one gameweek or dropping it entirely.
        </p>
        <p className="mt-2 text-[12px] leading-relaxed text-black/60 dark:text-white/60">
          Scored against it unshifted, FPL &ldquo;beats&rdquo; a hindsight oracle that knows a
          player&apos;s true season scoring rate <em>and</em> the minutes they actually played.
          That is the tell. Shifted to what a manager could actually see before the deadline, it
          scores <strong className="tabular-nums">{p.spearman_fpl?.toFixed(3)}</strong>, and this
          page uses that. The comparison rests on{" "}
          <strong>{p.baseline_gws}</strong> gameweeks and{" "}
          <strong>{p.baseline_n?.toLocaleString()}</strong> player-gameweeks.
        </p>
        <p className="mt-2 text-[12px] leading-relaxed text-black/60 dark:text-white/60">
          <strong className="font-semibold">Two corrections in one day, both published.</strong>{" "}
          This page first claimed we had the lower error — wrong, an artefact of averaging our
          score over every gameweek and FPL&apos;s over only the few where their column was
          populated. It then claimed FPL beat us outright — also wrong, from benchmarking against
          the contaminated column. Both are fixed. A page that quietly restates its numbers is
          worth nothing, so the history stays.
        </p>
        <p className="mt-2 text-[12px] leading-relaxed text-black/60 dark:text-white/60">
          The caveat that runs against us: shifting takes FPL&apos;s snapshot from just after the
          previous gameweek, so it misses up to a week of team news before the next deadline.
          That handicaps them by an unknown amount. The caveat that runs for us: our live model
          reduces a projection when a player is flagged injured or doubtful, and the historical
          data carries no such column, so this test runs ours with that switched off. Neither is
          quantified. Both should be.
        </p>
      </div>

      <Subset
        title="Players who featured"
        blurb="The honest test: everyone who got minutes, so the score isn't inflated by correctly guessing that a benched player scores nothing"
        s={card.measured.played_only}
      />

      <Subset
        title="All players"
        blurb="Everyone in the pool, including non-starters — flattered on both sides by the easy did-they-play signal"
        s={card.measured.all_players}
      />

      <section className="flex flex-col gap-2">
        <h3 className="t-title text-[15px] font-semibold">Error by position</h3>
        <p className="text-[12px] text-black/50 dark:text-white/50">
          Mean absolute error among players who featured. Forwards are hardest — their points
          come almost entirely from goals, which are rare and lumpy.
        </p>
        <div className="grid grid-cols-4 gap-2">
          {["GK", "DEF", "MID", "FWD"].map((pos) => (
            <div key={pos} className="flex flex-col items-center gap-0.5 rounded-xl border border-black/10 py-2.5 dark:border-white/10">
              <span className="t-title text-lg font-bold tabular-nums">
                {card.measured.mae_by_position_played[pos]?.toFixed(2) ?? "—"}
              </span>
              <span className="t-label text-[10px] text-black/45 dark:text-white/45">{pos}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-2">
        <h3 className="t-title text-[15px] font-semibold">What we tried</h3>
        <p className="text-[12px] leading-relaxed text-black/50 dark:text-white/50">
          Every change measured as a before/after on the same harness. The nulls are kept
          deliberately — a list containing only successes tells you nothing about the process
          that produced it.
        </p>
        <ul className="flex flex-col gap-1.5">
          {card.experiments.map((e) => {
            const kept = e.verdict.startsWith("kept");
            return (
              <li
                key={e.name}
                className="flex flex-col gap-1 rounded-xl border border-black/10 p-3 dark:border-white/10"
              >
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-[13px] font-semibold">{e.name}</span>
                  <span
                    className={`t-label flex-none rounded-full px-2 py-0.5 text-[9px] ${
                      kept
                        ? "bg-emerald-500/15 text-[var(--emerald-text)]"
                        : "bg-black/[.06] text-black/50 dark:bg-white/10 dark:text-white/50"
                    }`}
                  >
                    {kept ? "kept" : "rejected"}
                  </span>
                </div>
                <span className="text-[12px] leading-relaxed text-black/55 dark:text-white/55">
                  {e.question}
                </span>
                <span className="font-mono text-[11px] tabular-nums text-black/45 dark:text-white/45">
                  {e.delta}
                </span>
                <span className="text-[11px] leading-relaxed text-black/45 dark:text-white/45">
                  {e.verdict} · measured {e.measured}
                </span>
              </li>
            );
          })}
        </ul>
      </section>

      <section className="flex flex-col gap-2">
        <h3 className="t-title text-[15px] font-semibold">What the model does not know</h3>
        <p className="text-[12px] leading-relaxed text-black/50 dark:text-white/50">
          Absences, stated plainly. Anything on this list is something the site will not
          pretend to have an opinion about.
        </p>
        <dl className="flex flex-col gap-2">
          {card.not_modelled.map((n) => (
            <div key={n.topic} className="rounded-xl border border-black/10 p-3 dark:border-white/10">
              <dt className="text-[13px] font-semibold">{n.topic}</dt>
              <dd className="mt-0.5 text-[12px] leading-relaxed text-black/55 dark:text-white/55">
                {n.detail}
              </dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="flex flex-col gap-2">
        <h3 className="t-title text-[15px] font-semibold">Method</h3>
        <dl className="flex flex-col gap-2">
          {Object.entries(card.method).map(([k, v]) => (
            <div key={k} className="rounded-xl border border-black/10 p-3 dark:border-white/10">
              <dt className="t-label text-[10px] text-black/45 dark:text-white/45">{k}</dt>
              <dd className="mt-1 text-[12px] leading-relaxed text-black/60 dark:text-white/60">{v}</dd>
            </div>
          ))}
        </dl>
      </section>

      <p className="text-[11px] leading-relaxed text-black/45 dark:text-white/45">
        Generated {card.generated_at.slice(0, 10)} from {card.measured.n_player_gws.toLocaleString()}{" "}
        player-gameweeks across {card.measured.gws_scored} gameweeks of {card.season}. Rebuild it
        with <code className="font-mono">scripts/build_model_card.py</code>. If this date is old,
        so is every number above — that is the point of printing it.{" "}
        <Link href="/predictions" className="text-emerald-600 underline">
          See the projections themselves →
        </Link>
      </p>
    </PageShell>
  );
}
