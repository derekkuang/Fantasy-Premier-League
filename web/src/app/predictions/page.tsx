import { getLatestGw, getPredictions } from "@/lib/api";
import { PredictionsTable } from "@/components/predictions-table";
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
      subtitle="Per-player expected points for the gameweek — filter and sort."
      meta={<span className="rounded-full bg-black/5 px-2 py-1 font-mono text-[11px] text-black/50 dark:bg-white/10 dark:text-white/50">{data.meta.model_ver}</span>}
    >
      <PredictionsTable predictions={data.predictions} />
    </PageShell>
  );
}
