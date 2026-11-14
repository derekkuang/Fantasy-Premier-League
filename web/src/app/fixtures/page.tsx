import { getFixtures, getLatestGw } from "@/lib/api";
import { FixtureTicker } from "@/components/fixture-ticker";
import { JerseyDefs } from "@/components/jersey";
import { PageError, PageShell } from "@/components/page-shell";

export default async function FixturesPage() {
  let data;
  try {
    data = await getFixtures(await getLatestGw());
  } catch {
    return <PageError message="The fixtures couldn't be loaded. Try again in a minute." />;
  }
  return (
    <PageShell
      title="Fixtures"
      subtitle="How hard each team's next games are, best runs first."
    >
      {/* defines the #jerseyBody clip path every <Jersey/> references — render once */}
      <JerseyDefs />
      <FixtureTicker data={data} />
    </PageShell>
  );
}
