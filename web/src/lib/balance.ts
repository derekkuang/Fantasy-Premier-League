// Client port of fpledge.balance.check_balance — the structural squad-health flags. Kept
// faithful to the backend (same thresholds + messages) so it matches the server baseline
// on the recommended XI, then updates live as the user swaps bench <-> starters.

import type { SquadPlayer } from "@/lib/api";

const TEMPLATE_EO = 40.0; // ownership% at/above which a pick is "template"
const DIFFERENTIAL_EO = 10.0; // below which a pick is a "differential"
const ROTATION_MINUTES = 60.0; // expected minutes below which a starter is a rotation risk
const DEAD_BENCH_MINUTES = 20.0; // bench player below this won't provide auto-sub cover
const BENCH_SPEND_WARN = 18.0; // £m on the bench beyond which too much budget isn't scoring

/** A flag, plus the players it is actually about.
 *
 *  `message` stays byte-identical to the backend's — that parity is the point of this
 *  module. `detail` is additive and UI-only: a warning that says "3 starters are rotation
 *  risks" without naming them makes the reader go hunting through the pitch to find out
 *  who. Naming them is the difference between a verdict and something you can act on. */
export type BalanceFlag = {
  level: "warn" | "info" | "ok";
  message: string;
  detail?: { note: string; rows: { name: string; value: string }[] };
};

const round1 = (n: number) => Math.round(n * 10) / 10;

const byName = (a: SquadPlayer, b: SquadPlayer) => a.web_name.localeCompare(b.web_name);

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
    flags.push({
      level: "warn",
      message: `£${benchSpend.toFixed(1)}m on the bench — a lot of budget not scoring`,
      detail: {
        note: `Budget parked on players who only score if someone ahead of them doesn't play. Warns above £${BENCH_SPEND_WARN.toFixed(0)}m.`,
        rows: [...bench].sort((a, b) => b.price - a.price)
          .map((p) => ({ name: p.web_name, value: `£${p.price.toFixed(1)}m · ${p.xp.toFixed(1)} xP` })),
      },
    });

  if (deadBench >= 2)
    flags.push({
      level: "warn",
      message: `${deadBench} bench players unlikely to play — weak auto-sub cover`,
      detail: {
        note: `Under ${DEAD_BENCH_MINUTES} expected minutes, so they can't be relied on to cover a starter who blanks.`,
        rows: bench.filter((p) => (p.x_minutes ?? 90) < DEAD_BENCH_MINUTES).sort(byName)
          .map((p) => ({ name: p.web_name, value: `${Math.round(p.x_minutes ?? 0)}′ expected` })),
      },
    });

  if (topTwoClubs >= 6)
    flags.push({
      level: "warn",
      message: `${topTwoClubs}/${squad.length} players from just two clubs — concentration risk`,
      detail: {
        note: "One bad afternoon for either club takes a large share of your squad with it.",
        rows: [...teamCounts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 2)
          .map(([club, n]) => ({
            name: club,
            value: `${n} · ${squad.filter((p) => (p.team ?? "?") === club).sort(byName).map((p) => p.web_name).join(", ")}`,
          })),
      },
    });

  if (nDifferential >= 5)
    flags.push({
      level: "warn",
      message: `${nDifferential} differentials in the XI — high variance`,
      detail: {
        note: `Owned by under ${DIFFERENTIAL_EO}% of managers. They win you rank when they return and cost you nothing when they blank — the swing cuts both ways.`,
        rows: xi.filter((p) => p.ownership < DIFFERENTIAL_EO).sort((a, b) => a.ownership - b.ownership)
          .map((p) => ({ name: p.web_name, value: `${p.ownership.toFixed(1)}% owned` })),
      },
    });

  if (nRotation >= 3)
    flags.push({
      level: "warn",
      message: `${nRotation} starters are rotation/minutes risks`,
      detail: {
        note: `Under ${ROTATION_MINUTES} expected minutes. Their xP is already reduced to match — this flags how much of your XI rests on it.`,
        rows: xi.filter((p) => (p.x_minutes ?? 90) < ROTATION_MINUTES).sort((a, b) => (a.x_minutes ?? 90) - (b.x_minutes ?? 90))
          .map((p) => ({ name: p.web_name, value: `${Math.round(p.x_minutes ?? 0)}′ expected` })),
      },
    });

  if (nTemplate >= 9)
    flags.push({
      level: "info",
      message: `very template XI (${nTemplate}/11 highly owned) — safe but low ceiling`,
      detail: {
        note: `Owned by ${TEMPLATE_EO}% or more. You move with the field rather than away from it: hard to fall behind, equally hard to climb.`,
        rows: xi.filter((p) => p.ownership >= TEMPLATE_EO).sort((a, b) => b.ownership - a.ownership)
          .map((p) => ({ name: p.web_name, value: `${p.ownership.toFixed(1)}% owned` })),
      },
    });

  if (captainDependence > 0.5)
    flags.push({
      level: "info",
      message: `${Math.round(captainDependence * 100)}% of XI xP from your top 3 — captain-dependent`,
      detail: {
        note: `${top3.toFixed(1)} of ${xiXp.toFixed(1)} projected points sit with three players. A quiet week from them is a quiet week overall.`,
        rows: [...xi].sort((a, b) => b.xp - a.xp).slice(0, 3)
          .map((p) => ({ name: p.web_name, value: `${p.xp.toFixed(1)} xP` })),
      },
    });

  if (!flags.some((f) => f.level === "warn"))
    flags.push({ level: "ok", message: "no structural warnings — squad looks balanced" });

  return { flags };
}
