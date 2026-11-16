import { getFixtures, getLatestGw, getMatches } from "@/lib/api";
import { oddsByFixture } from "@/lib/odds";
import { FixtureTicker } from "@/components/fixture-ticker";
import { JerseyDefs } from "@/components/jersey";
import { PageError, PageShell } from "@/components/page-shell";

export default async function FixturesPage() {
  let data;
  let odds = {};
  try {
    const gw = await getLatestGw();
    // The win and clean-sheet chances live on the matches payload. Without it the grid still
    // works: those two views print a dash and the fixtures don't link.
    const [fixtures, matches] = await Promise.all([getFixtures(gw), getMatches(gw).catch(() => null)]);
    data = fixtures;
    if (matches) odds = oddsByFixture(matches.matches);
  } catch {
    return <PageError message="The fixtures couldn't be loaded. Try again in a minute." />;
  }
  return (
    <PageShell
      title="Fixtures"
      subtitle="How hard each team's next games are, best runs first. Tap a fixture for its Match Lab."
    >
      {/* defines the #jerseyBody clip path every <Jersey/> references — render once */}
      <JerseyDefs />
      <FixtureTicker data={data} odds={odds} />
    </PageShell>
  );
}
