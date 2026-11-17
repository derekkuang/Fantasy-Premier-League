// Match Lab (docs/MATCH_LAB.md): one gameweek's matches as cards, each opening its own page.
// Fixtures is the planning grid across eight gameweeks; this is the place to study one.

import type { Metadata } from "next";
import { getLatestGw, getMatches, getPredictions, type Match, type Prediction } from "@/lib/api";
import { isFlagged, modelGap } from "@/lib/match-lab";
import { JerseyDefs } from "@/components/jersey";
import { MatchHub, type HubMatch, type HubPick } from "@/components/match-hub";
import { PageError, PageShell } from "@/components/page-shell";

export const metadata: Metadata = {
  title: "Match Lab — FPL Edge",
  description: "Every Premier League match this gameweek: the odds, our model's view, the predicted lineups and the best FPL picks.",
  alternates: { canonical: "/match-lab" },
};

/** The best pick from one side: this gameweek's expected points, or the fixture's own for a later one. */
function bestPick(preds: Prediction[], team: string | null, opp: string | null, gw: number, current: number): HubPick | null {
  let best: HubPick | null = null;
  for (const p of preds) {
    if (p.team !== team) continue;
    const xp = gw === current ? p.xp : p.fixtures.find((f) => f.gw === gw && f.opp === opp)?.xp;
    if (xp == null) continue;
    if (!best || xp > best.xp) best = { id: p.element_id, name: p.web_name, xp };
  }
  return best;
}

/** Everything a card needs and nothing more: the full player list stays on the server. */
function summarise(m: Match, preds: Prediction[], current: number): HubMatch {
  const flagged = (team: string | null) => (m.gw === current ? preds.filter((p) => p.team === team && isFlagged(p)).length : null);
  return {
    id: m.match_id, gw: m.gw, home: m.home, away: m.away, kickoff: m.kickoff ?? null,
    result: m.result, lam_home: m.lam_home, lam_away: m.lam_away, clean_sheet: m.clean_sheet,
    source: m.source, gap: modelGap(m),
    flagged: { home: flagged(m.home), away: flagged(m.away) },
    pick: { home: bestPick(preds, m.home, m.away, m.gw, current), away: bestPick(preds, m.away, m.home, m.gw, current) },
  };
}

export default async function MatchLabPage() {
  let gw: number;
  let cards: HubMatch[];
  try {
    gw = await getLatestGw();
    const [matches, preds] = await Promise.all([getMatches(gw), getPredictions(gw)]);
    cards = matches.matches.map((m) => summarise(m, preds.predictions, gw));
  } catch {
    return <PageError message="The matches couldn't be loaded. Try again in a minute." />;
  }
  return (
    <PageShell title="Match Lab" subtitle="Every match in the gameweek: the odds, our model's view, the lineups and the best picks. Tap one to dig in.">
      <JerseyDefs />
      <MatchHub cards={cards} current={gw} />
    </PageShell>
  );
}
