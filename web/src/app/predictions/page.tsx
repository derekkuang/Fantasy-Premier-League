import { getLatestGw, getPredictions } from "@/lib/api";
import { PredictionsExplorer } from "@/components/predictions-table";
import { JerseyDefs } from "@/components/jersey";
import { PageError, PageShell } from "@/components/page-shell";

export default async function PredictionsPage() {
  let data;
  try {
    data = await getPredictions(await getLatestGw());
  } catch (err) {
    return <PageError message={(err as Error).message} />;
  }
  return (
    <PageShell
      title="Predictions"
      subtitle="Rank every player by this gameweek or a 3-week outlook — tap a row for the fixture run and full xP breakdown."
      meta={<span className="rounded-full bg-black/5 px-2 py-1 font-mono text-[11px] text-black/50 dark:bg-white/10 dark:text-white/50">{data.meta.model_ver}</span>}
    >
      {/* defines the #jerseyBody clip path every <Jersey/> references — render once */}
      <JerseyDefs />
      <PredictionsExplorer predictions={data.predictions} />
      {/* affiliation + kit notices live in the global footer */}
      <p className="text-center text-[11px] leading-relaxed text-black/55 dark:text-white/60">
        xP is model-estimated: the mean points a player would score across many simulated
        gameweeks, not a forecast of what they will score in this one.
      </p>
    </PageShell>
  );
}
