// The footer: one line of disclaimer and the links that don't belong in the main navigation.
// The full legal text (non-affiliation, trade marks, data source) is on the Terms page.

import Link from "next/link";

const LINKS: [string, string][] = [
  ["/model", "How the model does"],
  ["/privacy", "Privacy"],
  ["/terms", "Terms"],
];

export function Footer() {
  return (
    <footer className="mt-8 border-t border-[var(--line)]">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-2 px-4 py-6">
        <nav aria-label="Footer" className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
          <span className="t-title text-[14px] font-bold">
            FPL<span className="text-emerald-600">Edge</span>
          </span>
          {LINKS.map(([href, label]) => (
            <Link key={href} href={href} className="text-[13px] text-muted hover:text-[var(--emerald-text)]">
              {label}
            </Link>
          ))}
        </nav>
        <p className="text-[12px] leading-relaxed text-muted">
          An independent tool, not affiliated with the Premier League or Fantasy Premier League.
          Projections are model estimates, not advice. © {new Date().getFullYear()} FPL Edge.
        </p>
      </div>
    </footer>
  );
}
