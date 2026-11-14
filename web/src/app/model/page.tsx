// How the model does. One headline (this season, against FPL's own forecast, week by week) and
// everything else one tap away: each gameweek, last season's full test and the corrections it
// went through, what we tried, what the model doesn't know, how it works, and how the team
// news is checked.
//
// Nothing on this page is written by hand except the notes. The live record comes from the
// daily precompute (live_record.json), last season's test from the model card, and the notes
// from fpledge/model_notes.py. A record that doesn't exist yet says so rather than inventing one.

import type { Metadata } from "next";
import Link from "next/link";
import { getModelCard, getNews, type CardSubset, type ModelCard, type NewsResponse } from "@/lib/api";
import { PageError, PageShell } from "@/components/page-shell";
import { Fold } from "@/components/fold";
import { LiveChart } from "@/components/live-chart";

export const metadata: Metadata = {
  title: "How the model does — FPL Edge",
  description:
    "This season's projections scored against what happened, week by week, beside FPL's own forecast. Plus last season's test, the experiments that failed and what the model doesn't know.",
  alternates: { canonical: "/model" },
};

export const revalidate = 3600;

function Pair({ label, mine, theirs, better, digits = 3, unit = "" }: {
  label: string; mine: number | null; theirs: number | null; better: "high" | "low"; digits?: number; unit?: string;
}) {
  if (mine == null || theirs == null) return null;
  const weWin = better === "high" ? mine > theirs : mine < theirs;
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-[var(--line)] py-1.5 text-[13px]">
      <span className="text-muted">{label}</span>
      <span className="tabular-nums">
        <strong className={weWin ? "text-[var(--emerald-text)]" : ""}>{mine.toFixed(digits)}{unit}</strong>
        <span className="text-muted"> ours · </span>
        <strong className={weWin ? "" : "text-[var(--emerald-text)]"}>{theirs.toFixed(digits)}{unit}</strong>
        <span className="text-muted"> FPL</span>
      </span>
    </div>
  );
}

function Subset({ title, s }: { title: string; s: CardSubset }) {
  return (
    <div className="flex flex-col">
      <span className="pb-1 text-[13px] font-semibold">{title} <span className="font-normal text-muted">· {s.n.toLocaleString()} player-gameweeks</span></span>
      <Pair label="Ranking score" mine={s.spearman_model} theirs={s.spearman_fpl} better="high" />
      <Pair label="Average miss" mine={s.mae_model} theirs={s.mae_fpl} better="low" digits={2} unit=" pts" />
    </div>
  );
}

export default async function ModelPage() {
  let card: ModelCard;
  try {
    card = await getModelCard();
  } catch {
    return <PageError message="The model's results aren't available right now. Try again in a minute." />;
  }
  let news: NewsResponse | null = null;
  try {
    news = await getNews();
  } catch {
    news = null;
  }

  const live = card.live ?? null;
  const sum = live?.summary ?? null;
  const p = card.measured.played_only;

  return (
    <PageShell title="How the model does" subtitle="This season's projections, scored against what actually happened.">
      {/* the headline */}
      <section className="flex flex-col gap-4 rounded-2xl border border-[var(--line)] p-4">
        {sum ? (
          <>
            <h2 className="t-title text-[18px] font-semibold leading-snug">
              {`In ${sum.ours_ahead} of ${sum.gws_compared} gameweeks, our projections ranked the players better than FPL's own forecast did.`}
            </h2>
            <div className="grid grid-cols-2 gap-2">
              <div className="flex flex-col gap-1 rounded-[12px] bg-[var(--chip)] px-3 py-2.5">
                <span className="t-title text-[24px] font-bold leading-none tabular-nums text-[var(--emerald-text)]">{sum.ours_rho.toFixed(2)}</span>
                <span className="text-[12px] text-muted">our average ranking score</span>
              </div>
              <div className="flex flex-col gap-1 rounded-[12px] bg-[var(--chip)] px-3 py-2.5">
                <span className="t-title text-[24px] font-bold leading-none tabular-nums">{sum.fpl_rho.toFixed(2)}</span>
                <span className="text-[12px] text-muted">FPL&apos;s, on the same players</span>
              </div>
            </div>
          </>
        ) : (
          <h2 className="t-title text-[18px] font-semibold">This season&apos;s record starts once a gameweek with FPL&apos;s forecast has finished.</h2>
        )}
        {live && <LiveChart live={live} />}
        <p className="text-[13px] leading-relaxed text-muted">
          The ranking score measures how well the predicted order of players matched the order they
          actually scored in (1 is perfect). Around 0.3 means single gameweeks stay mostly
          unpredictable, for everyone: an edge in the ordering, not a promise about any player.
        </p>
      </section>

      <div className="flex flex-col">
        {live && live.gws.length > 0 && (
          <Fold title="Each gameweek" aside={`${live.gws.length} finished`}>
            <table className="w-full text-[13px] tabular-nums">
              <thead>
                <tr className="text-[12px] text-muted">
                  <th className="py-1 text-left font-normal">GW</th>
                  <th className="py-1 text-right font-normal">Players</th>
                  <th className="py-1 text-right font-normal">Ours</th>
                  <th className="py-1 text-right font-normal">FPL</th>
                  <th className="hidden py-1 text-right font-normal sm:table-cell">Our miss</th>
                  <th className="hidden py-1 text-right font-normal sm:table-cell">FPL miss</th>
                </tr>
              </thead>
              <tbody>
                {[...live.gws].reverse().map((w) => (
                  <tr key={w.gw} className="border-t border-[var(--line)]">
                    <td className="py-1.5">{w.gw}</td>
                    <td className="py-1.5 text-right">{w.n}</td>
                    <td className="py-1.5 text-right font-semibold">{w.ours.rho?.toFixed(2) ?? "–"}</td>
                    <td className="py-1.5 text-right">{w.fpl?.rho?.toFixed(2) ?? "not captured"}</td>
                    <td className="hidden py-1.5 text-right sm:table-cell">{w.ours.mae.toFixed(2)}</td>
                    <td className="hidden py-1.5 text-right sm:table-cell">{w.fpl ? w.fpl.mae.toFixed(2) : "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-[12px] leading-relaxed text-muted">
              Scored on players we projected who got minutes. Where this site captured FPL&apos;s
              forecast before the deadline, both are scored on exactly the same players. Projections
              are the ones published before each deadline, so earlier weeks show earlier versions of
              the model. &ldquo;Miss&rdquo; is the average gap between projected and actual points.
            </p>
          </Fold>
        )}

        <Fold title={`Last season's test (${card.season})`} aside={`run ${card.generated_at.slice(0, 10)}`}>
          <div className="flex flex-col gap-4">
            <p className="text-[13px] leading-relaxed">
              {`The model was walked through ${card.season} a gameweek at a time, seeing only earlier weeks each time, and scored against FPL's forecast as it stood before each deadline.`}
            </p>
            <Subset title="Players who featured" s={card.measured.played_only} />
            <Subset title="All players" s={card.measured.all_players} />
            <div className="flex flex-col gap-1">
              <span className="text-[13px] font-semibold">Average miss by position, players who featured</span>
              <div className="grid grid-cols-4 gap-2">
                {["GK", "DEF", "MID", "FWD"].map((pos) => (
                  <div key={pos} className="flex flex-col items-center rounded-[10px] bg-[var(--chip)] py-2">
                    <span className="text-[16px] font-bold tabular-nums">{card.measured.mae_by_position_played[pos]?.toFixed(2) ?? "–"}</span>
                    <span className="text-[12px] text-muted">{pos}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="flex flex-col gap-2 text-[13px] leading-relaxed text-muted">
              <p>
                <strong className="text-[var(--fg)]">Two corrections, both kept on the record.</strong>{" "}
                This page first claimed the lower average miss; that came from averaging our score
                over every gameweek and FPL&apos;s over only the few where its numbers existed. It then
                claimed FPL ranked better; that came from a copy of FPL&apos;s forecast scraped after
                each gameweek, which had already absorbed the result. Shifted to what a manager could
                see before the deadline, FPL scores {p.spearman_fpl?.toFixed(3)} over {p.baseline_gws}{" "}
                gameweeks, the figure used above.
              </p>
              <p>
                That shift misses up to a week of FPL&apos;s team news, which handicaps FPL by an
                unknown amount; and this test ran our model without the injury flags it uses live,
                which handicaps us. This season&apos;s record above has neither problem.
              </p>
            </div>
          </div>
        </Fold>

        <Fold title="What we tried" aside={`${card.experiments.length} experiments`}>
          <ul className="flex flex-col">
            {card.experiments.map((e) => {
              const kept = e.verdict.startsWith("kept");
              return (
                <li key={e.name} className="flex flex-col gap-0.5 border-t border-[var(--line)] py-2.5 first:border-t-0">
                  <span className="flex items-baseline justify-between gap-3">
                    <span className="text-[14px] font-semibold">{e.name}</span>
                    <span className={`flex-none rounded-full px-2 py-0.5 text-[12px] font-semibold ${kept ? "bg-emerald-500/15 text-[var(--emerald-text)]" : "bg-[var(--chip)] text-muted"}`}>
                      {kept ? "kept" : "dropped"}
                    </span>
                  </span>
                  <span className="text-[13px] text-muted">{e.question}</span>
                  <span className="text-[13px] tabular-nums">{e.delta}</span>
                  <span className="text-[12px] text-muted">{e.verdict} · {e.measured}</span>
                </li>
              );
            })}
          </ul>
        </Fold>

        <Fold title="What the model doesn't know" aside={`${card.not_modelled.length} things`}>
          <dl className="flex flex-col">
            {card.not_modelled.map((n) => (
              <div key={n.topic} className="border-t border-[var(--line)] py-2.5 first:border-t-0">
                <dt className="text-[14px] font-semibold">{n.topic}</dt>
                <dd className="text-[13px] leading-relaxed text-muted">{n.detail}</dd>
              </div>
            ))}
          </dl>
        </Fold>

        <Fold title="How it works">
          <dl className="flex flex-col">
            {Object.entries(card.method).map(([k, v]) => (
              <div key={k} className="border-t border-[var(--line)] py-2.5 first:border-t-0">
                <dt className="text-[14px] font-semibold first-letter:uppercase">{k}</dt>
                <dd className="text-[13px] leading-relaxed text-muted">{v}</dd>
              </div>
            ))}
          </dl>
        </Fold>

        {news && (
          <Fold title="How the team news is checked" className="border-b">
            <div className="flex flex-col gap-2 text-[13px] leading-relaxed">
              <p>
                The news page tags stories by keyword (&ldquo;injury&rdquo;, &ldquo;rotation&rdquo;)
                and compares each tagged player with FPL&apos;s own status. Today{" "}
                <strong className="tabular-nums">
                  {news.quality.precision == null ? "none" : `${Math.round(news.quality.precision * 100)}%`}
                </strong>{" "}
                of those tags agree with FPL, and{" "}
                <strong className="tabular-nums">{news.quality.additive}</strong>{" "}name players FPL
                hasn&apos;t flagged, unverified.
              </p>
              <p className="text-muted">
                That&apos;s too low to show the tags on the news page, so it shows FPL&apos;s status
                instead. Out of {news.n_items.toLocaleString()} stories collected; none of it changes a
                projection.
              </p>
            </div>
          </Fold>
        )}
      </div>

      <p className="text-[13px] text-muted">
        This season&apos;s record updates every day.{" "}
        <Link href="/players" className="text-[var(--emerald-text)] underline">See the projections</Link>
      </p>
    </PageShell>
  );
}
