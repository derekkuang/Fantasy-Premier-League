// One match (HANDOFF §40): reached from any fixture on the Fixtures grid.

import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getLatestGw, getMatch, type MatchResponse } from "@/lib/api";
import { JerseyDefs } from "@/components/jersey";
import { MatchLab } from "@/components/match-lab";
import { PageError, PageShell } from "@/components/page-shell";

type Params = { params: Promise<{ match: string }> };

// "11-2-20": the gameweek, then the home and away clubs' FPL ids.
const MATCH_ID = /^\d{1,2}-\d{1,2}-\d{1,2}$/;

async function load(id: string): Promise<{ gw: number; data: MatchResponse } | "missing" | "error"> {
  if (!MATCH_ID.test(id)) return "missing";
  try {
    const gw = await getLatestGw();
    return { gw, data: await getMatch(gw, id) };
  } catch (e) {
    // the API answers 404 for a match outside the current window (played, or not yet projected)
    return e instanceof Error && e.message.includes("404") ? "missing" : "error";
  }
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { match } = await params;
  const got = await load(match);
  if (typeof got === "string") return { title: "Match — FPL Edge" };
  const m = got.data.match;
  return {
    title: `${m.home} v ${m.away}, gameweek ${m.gw} — FPL Edge`,
    description: `Win, draw and clean-sheet chances, the likeliest scores and both predicted lineups for ${m.home} v ${m.away}.`,
    alternates: { canonical: `/fixtures/${match}` },
  };
}

export default async function MatchPage({ params }: Params) {
  const { match } = await params;
  const got = await load(match);
  if (got === "missing") notFound();
  if (got === "error") return <PageError message="This match couldn't be loaded. Try again in a minute." />;
  const { gw, data } = got;
  const m = data.match;
  return (
    <PageShell
      back={{ href: "/fixtures", label: "Fixtures" }}
      title={`${m.home} v ${m.away}`}
      subtitle={`Gameweek ${m.gw} · ${m.source === "market" ? "odds from the bookmakers" : "odds from our match model"}`}
    >
      <JerseyDefs />
      <MatchLab match={m} assets={data.assets} gw={gw} />
    </PageShell>
  );
}
