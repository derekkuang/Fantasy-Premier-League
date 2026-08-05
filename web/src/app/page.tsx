// Home page.
//
// One action, then proof. The previous version led with the FPL-team-id field, which is the
// one path that cannot work before the first deadline — the FPL API exposes no manager squads
// until then, so every real id a visitor typed returned a 404 through the whole preseason
// acquisition window. Building a squad works today, for anyone, with nothing to look up, and
// the result is a shareable link. So that is the button, and the id field folds away beneath it.
//
// The proof strip is REAL data from the live payload, not a mocked screenshot. On a site whose
// entire position is "we show you our working", an illustrative fake squad would be the one
// thing on the page we couldn't stand behind.

import Link from "next/link";
import { getLatestGw, getPredictions, type Prediction } from "@/lib/api";
import { getClub } from "@/lib/clubs";
import { Jersey } from "@/components/jersey";
import { TeamSearch } from "@/components/team-search";

export const revalidate = 3600;

const PAGES: [string, string, string][] = [
  ["/predictions", "Every player, ranked", "Projected points for all 555, with the per-term maths behind each one."],
  ["/fixtures", "Two difficulty ratings", "Attack and defence disagree on about half of all fixtures. Most tickers show one number."],
  ["/differentials", "Risk, banded", "High projection, low ownership — sorted by how much of a punt it actually is."],
];

async function topPicks(): Promise<{ gw: number; players: Prediction[] } | null> {
  try {
    const gw = await getLatestGw();
    const { predictions } = await getPredictions(gw);
    const players = predictions
      .filter((p) => !p.low_coverage)
      .sort((a, b) => b.xp - a.xp)
      .slice(0, 4);
    return players.length ? { gw, players } : null;
  } catch {
    return null;   // a landing page must never depend on the API being up
  }
}

export default async function Home() {
  const top = await topPicks();

  return (
    <main className="mx-auto flex w-full max-w-lg flex-1 flex-col justify-center gap-7 px-5 py-14">
      <div className="flex flex-col gap-3 text-center">
        <h1 className="t-display text-[34px] font-bold sm:text-[42px]">
          Pick 15. See what they&apos;ll <span className="text-emerald-600">score.</span>
        </h1>
        <p className="text-[15px] leading-relaxed text-black/60 dark:text-white/60">
          A projected score for every player, the captain that gains you most on the field,
          and a squad-health check — from a match model, not a tip sheet.
        </p>
      </div>

      <div className="flex flex-col gap-3.5">
        <Link
          href="/squad"
          className="press flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-5 py-3.5 text-[15px] font-semibold text-white hover:bg-emerald-500"
        >
          Build a squad <span aria-hidden>→</span>
        </Link>
        <p className="text-center text-xs text-black/45 dark:text-white/45">
          £100m, 2/5/5/3, max 3 per club — the real rules. No account, no team id.
        </p>
        <TeamSearch collapsible />
      </div>

      {/* Live proof: the actual top of the actual table, rendered by the actual components. */}
      {top && (
        <Link
          href="/predictions"
          className="press flex flex-col gap-2 rounded-2xl border border-black/10 p-3 hover:border-emerald-600/50 dark:border-white/10"
        >
          <span className="t-label flex items-baseline justify-between text-[10px] text-black/40 dark:text-white/40">
            <span>Top projected · GW{top.gw}</span>
            <span className="normal-case tracking-normal text-emerald-600">see all →</span>
          </span>
          <span className="grid grid-cols-4 gap-2">
            {top.players.map((p) => {
              const club = getClub(p.team);
              return (
                <span key={p.element_id} className="flex flex-col items-center gap-1">
                  <Jersey
                    primary={club.primary}
                    secondary={club.secondary}
                    pattern={club.pattern}
                    width={30}
                    height={28}
                    className="block"
                  />
                  <span className="max-w-full truncate text-[11px] font-semibold">{p.web_name}</span>
                  <span className="t-title text-[15px] font-bold tabular-nums text-emerald-600">
                    {p.xp.toFixed(1)}
                  </span>
                </span>
              );
            })}
          </span>
        </Link>
      )}

      {/* Three doors, not four claims. Each one is a page you can go and check. */}
      <ul className="flex flex-col gap-2">
        {PAGES.map(([href, title, sub]) => (
          <li key={href}>
            <Link
              href={href}
              className="press flex items-center justify-between gap-3 rounded-xl border border-black/10 px-3.5 py-2.5 hover:border-emerald-600/50 dark:border-white/10"
            >
              <span className="flex flex-col">
                <span className="text-sm font-semibold">{title}</span>
                <span className="text-xs leading-relaxed text-black/50 dark:text-white/50">{sub}</span>
              </span>
              <span aria-hidden className="flex-none text-black/25 dark:text-white/25">→</span>
            </Link>
          </li>
        ))}
      </ul>

      <p className="text-center text-xs leading-relaxed text-black/55 dark:text-white/60">
        <strong className="font-semibold text-black/75 dark:text-white/75">Honest by design.</strong>{" "}
        We measured our projections against FPL&apos;s own and published the result —
        including the two times we got the measurement wrong. Single gameweeks stay mostly
        unpredictable; the tooling is the rest of the edge.{" "}
        <Link href="/model" className="whitespace-nowrap text-emerald-600 underline">
          see the numbers →
        </Link>
      </p>
    </main>
  );
}
