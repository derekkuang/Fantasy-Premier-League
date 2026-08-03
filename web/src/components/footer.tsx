// Global footer: the disclaimers that must appear on every page, plus the legal links.
//
// These were previously repeated per-page. They belong here instead — the non-affiliation
// notice in particular has to be visible wherever a user lands, not just on the pages that
// happened to carry it.

import Link from "next/link";

const LINKS: [string, string][] = [
  ["/predictions", "Predictions"],
  ["/fixtures", "Fixtures"],
  ["/differentials", "Differentials"],
  ["/privacy", "Privacy"],
  ["/terms", "Terms"],
];

export function Footer() {
  return (
    <footer className="mt-8 border-t border-black/10 dark:border-white/10">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-3 px-4 py-6">
        <nav className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
          <span className="text-sm font-bold tracking-tight">
            FPL<span className="text-emerald-600">Edge</span>
          </span>
          {LINKS.map(([href, label]) => (
            <Link
              key={href}
              href={href}
              className="text-[12px] text-black/55 hover:text-emerald-600 dark:text-white/60"
            >
              {label}
            </Link>
          ))}
        </nav>

        <div className="flex flex-col gap-1.5 text-[11px] leading-relaxed text-black/55 dark:text-white/60">
          <p>
            FPL Edge is an independent, unofficial tool. It is{" "}
            <strong className="font-semibold">not affiliated with, endorsed by, or associated with</strong>{" "}
            the Premier League, Fantasy Premier League, or any football club. &ldquo;Premier
            League&rdquo; and &ldquo;Fantasy Premier League&rdquo; are trade marks of the Football
            Association Premier League Limited.
          </p>
          <p>
            Player and fixture data come from Fantasy Premier League&apos;s public API, which is
            undocumented and may change or stop working without notice. Club colours are applied
            factually to generic shirt shapes — no official kits, badges or crests are used.
          </p>
          <p>
            Everything here is a <strong className="font-semibold">model estimate</strong>, not a
            statement of fact, a guarantee of results, or betting advice. Expected points are
            probabilistic and will often be wrong for any single player or gameweek.
          </p>
        </div>

        <p className="text-[11px] text-black/55 dark:text-white/60">
          © {new Date().getFullYear()} FPL Edge. All rights reserved.
        </p>
      </div>
    </footer>
  );
}
