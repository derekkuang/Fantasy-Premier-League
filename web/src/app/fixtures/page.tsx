import { getFixtures } from "@/lib/api";
import { FixtureTicker } from "@/components/fixture-ticker";
import { PageError, PageShell } from "@/components/page-shell";

export default async function FixturesPage() {
  let data;
  try {
    data = await getFixtures(1);
  } catch (err) {
    return <PageError message={(err as Error).message} />;
  }
  return (
    <PageShell
      title="Fixture ticker"
      subtitle="True difficulty from the match model, not FPL's static FDR."
      meta={<span className="rounded-full bg-black/5 px-2 py-1 font-mono text-[11px] text-black/50 dark:bg-white/10 dark:text-white/50">{data.meta.model_ver}</span>}
    >
      <FixtureTicker data={data} />
    </PageShell>
  );
}
