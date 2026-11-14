// Players: Predictions and Differentials, merged. /predictions and /differentials redirect here
// (next.config.ts); ?view=low-owned opens the Low owned view.

import { Suspense } from "react";
import type { Metadata } from "next";
import { getLatestGw, getPredictions, toRow } from "@/lib/api";
import { JerseyDefs } from "@/components/jersey";
import { PageError, PageShell } from "@/components/page-shell";
import { PlayersExplorer } from "@/components/players-explorer";
import { PlayersFromUrl } from "@/components/players-from-url";

export const metadata: Metadata = {
  title: "Players — FPL Edge",
  description: "Every Premier League player's projected points, with low-owned picks, budget options and penalty takers.",
  alternates: { canonical: "/players" },
};

export const revalidate = 300;

export default async function PlayersPage() {
  const gw = await getLatestGw();
  let data;
  try {
    data = await getPredictions(gw);
  } catch {
    return <PageError message="The projections couldn't be loaded. Try again in a minute." />;
  }
  const rows = data.predictions.map(toRow);
  return (
    <PageShell title="Players" subtitle={`Projected points for gameweek ${data.meta.gw}. Tap a player for the detail.`}>
      {/* defines the #jerseyBody clip path every <Jersey/> references — render once */}
      <JerseyDefs />
      {/* The static page renders the default view; the URL's ?view= takes over in the browser. */}
      <Suspense fallback={<PlayersExplorer predictions={rows} gw={data.meta.gw} />}>
        <PlayersFromUrl predictions={rows} gw={data.meta.gw} />
      </Suspense>
    </PageShell>
  );
}
