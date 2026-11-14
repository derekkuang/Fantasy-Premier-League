// Build-your-own-squad. A Server Component that fetches the player pool and the fixture
// ticker once, then hands both to the client builder — the same two payloads the Predictions
// and Team pages already use, so this route adds no backend surface at all.

import { Suspense } from "react";
import type { Metadata } from "next";
import { fixturesByTeam, getFixtures, getLatestGw, getPredictions, toRow } from "@/lib/api";
import { PageError } from "@/components/page-shell";
import { SquadBuilder } from "@/components/squad-builder";

export const metadata: Metadata = {
  title: "Build a squad — FPL Edge",
  description:
    "Pick fifteen players under the real rules — £100m, 2/5/5/3, max three per club — and get a projected score, the best captain and a squad-health check. No team id needed.",
  alternates: { canonical: "/squad" },
};

export const revalidate = 300;

export default async function SquadPage() {
  const gw = await getLatestGw();

  let loaded;
  try {
    loaded = await Promise.all([getPredictions(gw), getFixtures(gw)]);
  } catch {
    return <PageError message="The player list couldn't be loaded. Try again in a minute." />;
  }
  const [predictions, fixtures] = loaded;

  return (
    // useSearchParams needs a suspense boundary during prerender.
    <Suspense fallback={null}>
      <SquadBuilder
        pool={predictions.predictions.map(toRow)}
        fixtures={fixturesByTeam(fixtures)}
        gw={gw}
        meta={predictions.meta}
      />
    </Suspense>
  );
}
