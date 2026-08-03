import { getFixtures, getLatestGw } from "@/lib/api";
import { FixtureTicker } from "@/components/fixture-ticker";
import { JerseyDefs } from "@/components/jersey";
import { PageError, PageShell } from "@/components/page-shell";

export default async function FixturesPage() {
  let data;
  try {
    data = await getFixtures(await getLatestGw());
  } catch (err) {
    return <PageError message={(err as Error).message} />;
  }
  return (
    <PageShell
      title="Fixture ticker"
      subtitle="True difficulty from the match model, not FPL's static FDR — attack and defence side by side."
      meta={<span className="rounded-full bg-black/5 px-2 py-1 font-mono text-[11px] text-black/50 dark:bg-white/10 dark:text-white/50">{data.meta.model_ver}</span>}
    >
      {/* defines the #jerseyBody clip path every <Jersey/> references — render once */}
      <JerseyDefs />
      <FixtureTicker data={data} />
      {/* affiliation + kit notices live in the global footer */}
      <p className="text-[11px] leading-relaxed text-black/55 dark:text-white/60">
        Difficulty is banded from the match model&apos;s expected goals for each side, so it moves
        with form and opponent — it is not FPL&apos;s fixed preseason rating.
      </p>
    </PageShell>
  );
}
