// Client port of fpledge.balance.check_balance — the structural squad-health flags. Kept
// faithful to the backend (same thresholds + messages) so it matches the server baseline
// on the recommended XI, then updates live as the user swaps bench <-> starters.

import type { SquadPlayer } from "@/lib/api";

const TEMPLATE_EO = 40.0; // ownership% at/above which a pick is "template"
const DIFFERENTIAL_EO = 10.0; // below which a pick is a "differential"
const ROTATION_MINUTES = 60.0; // expected minutes below which a starter is a rotation risk
const DEAD_BENCH_MINUTES = 20.0; // bench player below this won't provide auto-sub cover
const BENCH_SPEND_WARN = 18.0; // £m on the bench beyond which too much budget isn't scoring

export type BalanceFlag = [string, string]; // [level, message] — level: warn | info | ok

const round1 = (n: number) => Math.round(n * 10) / 10;

export function computeHealth(squad: SquadPlayer[], starterIds: Set<number>): { flags: BalanceFlag[] } {
  const xi = squad.filter((p) => starterIds.has(p.element_id));
  const bench = squad.filter((p) => !starterIds.has(p.element_id));

  const benchSpend = round1(bench.reduce((s, p) => s + p.price, 0));

  const teamCounts = new Map<string, number>();
  for (const p of squad) teamCounts.set(p.team ?? "?", (teamCounts.get(p.team ?? "?") ?? 0) + 1);
  const topTwoClubs = [...teamCounts.values()].sort((a, b) => b - a).slice(0, 2).reduce((a, b) => a + b, 0);

  const xiXp = xi.reduce((s, p) => s + p.xp, 0);
  const nTemplate = xi.filter((p) => p.ownership >= TEMPLATE_EO).length;
  const nDifferential = xi.filter((p) => p.ownership < DIFFERENTIAL_EO).length;
  const nRotation = xi.filter((p) => (p.x_minutes ?? 90) < ROTATION_MINUTES).length;
  const deadBench = bench.filter((p) => (p.x_minutes ?? 90) < DEAD_BENCH_MINUTES).length;
  const top3 = [...xi.map((p) => p.xp)].sort((a, b) => b - a).slice(0, 3).reduce((a, b) => a + b, 0);
  const captainDependence = xiXp > 0 ? top3 / xiXp : 0;

  const flags: BalanceFlag[] = [];
  if (benchSpend > BENCH_SPEND_WARN)
    flags.push(["warn", `£${benchSpend.toFixed(1)}m on the bench — a lot of budget not scoring`]);
  if (deadBench >= 2)
    flags.push(["warn", `${deadBench} bench players unlikely to play — weak auto-sub cover`]);
  if (topTwoClubs >= 6)
    flags.push(["warn", `${topTwoClubs}/${squad.length} players from just two clubs — concentration risk`]);
  if (nDifferential >= 5)
    flags.push(["warn", `${nDifferential} differentials in the XI — high variance`]);
  if (nRotation >= 3)
    flags.push(["warn", `${nRotation} starters are rotation/minutes risks`]);
  if (nTemplate >= 9)
    flags.push(["info", `very template XI (${nTemplate}/11 highly owned) — safe but low ceiling`]);
  if (captainDependence > 0.5)
    flags.push(["info", `${Math.round(captainDependence * 100)}% of XI xP from your top 3 — captain-dependent`]);
  if (!flags.some(([level]) => level === "warn"))
    flags.push(["ok", "no structural warnings — squad looks balanced"]);

  return { flags };
}
