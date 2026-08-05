"use client";
// Global top nav: makes the free content (fixtures, differentials, predictions) findable
// and hosts the theme toggle. Highlights the active route.

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ThemeToggle } from "@/components/theme-toggle";

const LINKS: [string, string][] = [
  ["/squad", "My squad"],
  ["/predictions", "Predictions"],
  ["/fixtures", "Fixtures"],
  ["/differentials", "Differentials"],
  ["/model", "The model"],
];

export function Nav() {
  const path = usePathname();
  return (
    // A translucent layer with the page passing underneath, and a soft edge below it
    // instead of a 1px rule — a hard divider reads as a seam between two documents, a
    // short fade reads as chrome floating over one. The height is fixed and published as
    // --nav-h so the sticky bars further down the page stop guessing at it.
    <nav className="chrome chrome-edge sticky top-0 z-30 h-[var(--nav-h)]">
      <div className="mx-auto flex h-full max-w-5xl items-center justify-between gap-2 px-4">
        <div className="flex items-center gap-1 overflow-x-auto">
          <Link href="/" className="press t-title mr-1 flex-none text-sm font-bold">
            FPL<span className="text-emerald-600">Edge</span>
          </Link>
          {LINKS.map(([href, label]) => {
            const active = path === href;
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={`press flex-none rounded-full px-3 py-1.5 text-[13px] font-medium ${
                  active
                    ? "bg-emerald-600 text-white"
                    : "text-black/55 hover:text-emerald-600 dark:text-white/55"
                }`}
              >
                {label}
              </Link>
            );
          })}
        </div>
        <ThemeToggle />
      </div>
    </nav>
  );
}
