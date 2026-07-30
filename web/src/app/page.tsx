// Home page. A Server Component (no "use client") — static hero markup, with the one
// interactive piece (<TeamSearch/>) imported as a client island.

import Link from "next/link";
import { TeamSearch } from "@/components/team-search";

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center gap-8 px-5 py-16">
      <div className="flex flex-col gap-3 text-center">
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
          Your gameweek, <span className="text-emerald-600">planned.</span>
        </h1>
        <p className="text-black/60 dark:text-white/60">
          Paste your FPL team ID for a projected score, the best captain, your best
          transfer (net of the −4 hit), and a squad-health check.
        </p>
      </div>

      <TeamSearch />

      <p className="-mt-4 text-center text-sm">
        <Link href="/team/0" className="text-black/50 underline hover:text-emerald-600 dark:text-white/50">
          or see a sample team →
        </Link>
      </p>

      <ul className="grid grid-cols-2 gap-3 text-sm">
        {[
          ["Projected points", "best XI + captain, doubled"],
          ["Best transfer", "ranked by xP, net of hits"],
          ["True fixture ticker", "from a live match model"],
          ["Squad health", "bench, balance, risk"],
        ].map(([title, sub]) => (
          <li
            key={title}
            className="rounded-xl border border-black/10 p-3 dark:border-white/10"
          >
            <div className="font-semibold">{title}</div>
            <div className="text-xs text-black/50 dark:text-white/50">{sub}</div>
          </li>
        ))}
      </ul>

      <p className="text-center text-[11px] text-black/40 dark:text-white/40">
        Honest by design: our xP is about on par with FPL&apos;s own — the edge is the
        tooling, not a magic forecast. Not affiliated with the Premier League.
      </p>
    </main>
  );
}
