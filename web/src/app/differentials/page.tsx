import { getPredictions } from "@/lib/api";
import { DifferentialsView } from "@/components/differentials-view";
import { PageError, PageShell } from "@/components/page-shell";

export default async function DifferentialsPage() {
  let data;
  try {
    data = await getPredictions(1);
  } catch (err) {
    return <PageError message={(err as Error).message} />;
  }
  return (
    <PageShell
      title="Differentials"
      subtitle="Low-owned, high-xP picks to climb rank."
      meta={<span className="rounded-full bg-black/5 px-2 py-1 font-mono text-[11px] text-black/50 dark:bg-white/10 dark:text-white/50">{data.meta.model_ver}</span>}
    >
      <DifferentialsView predictions={data.predictions} />
    </PageShell>
  );
}
