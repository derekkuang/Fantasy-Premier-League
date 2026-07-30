// Thin server wrapper: awaits the API on the server (params is a Promise in Next 16),
// fetches the team + fixture ticker, and hands the data to the interactive client
// dashboard. Errors render a friendly server-side fallback.

import Link from "next/link";
import { fixturesByTeam, getFixtures, getTeam, type TeamResponse, type TickerFixture } from "@/lib/api";
import { TeamDashboard } from "@/components/team-dashboard";

export default async function TeamPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  let data: TeamResponse;
  try {
    data = await getTeam(id);
  } catch (err) {
    return <ErrorState id={id} message={(err as Error).message} />;
  }

  // Fixture pips/sheet are a nice-to-have — if the ticker fails, the pitch still renders.
  let fixtures: Record<string, TickerFixture[]> = {};
  try {
    fixtures = fixturesByTeam(await getFixtures(data.gw));
  } catch {
    /* pips optional */
  }

  return <TeamDashboard data={data} fixtures={fixtures} />;
}

function ErrorState({ id, message }: { id: string; message: string }) {
  return (
    <main className="mx-auto flex max-w-md flex-col items-center gap-4 px-4 py-16 text-center">
      <h1 className="text-lg font-semibold">Couldn&apos;t load team {id}</h1>
      <p className="text-sm text-black/60 dark:text-white/60">{message}</p>
      <div className="flex flex-col gap-2 sm:flex-row">
        <Link
          href="/team/0"
          className="rounded-xl bg-emerald-600 px-5 py-2.5 font-semibold text-white hover:bg-emerald-500"
        >
          See the sample team
        </Link>
        <Link
          href="/"
          className="rounded-xl border border-black/15 px-5 py-2.5 font-semibold hover:bg-black/[.03] dark:border-white/15 dark:hover:bg-white/[.05]"
        >
          Try another ID
        </Link>
      </div>
    </main>
  );
}
