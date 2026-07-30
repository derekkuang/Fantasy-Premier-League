"use client";
// Global top nav: makes the free content (fixtures, differentials, predictions) findable
// and hosts the theme toggle. Highlights the active route.

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ThemeToggle } from "@/components/theme-toggle";

const LINKS: [string, string][] = [
  ["/predictions", "Predictions"],
  ["/fixtures", "Fixtures"],
  ["/differentials", "Differentials"],
];

export function Nav() {
  const path = usePathname();
  return (
    <nav className="sticky top-0 z-30 border-b border-black/10 bg-white/80 backdrop-blur dark:border-white/10 dark:bg-[#0a0a0a]/80">
      <div className="mx-auto flex max-w-5xl items-center justify-between gap-2 px-4 py-2.5">
        <div className="flex items-center gap-1 overflow-x-auto">
          <Link href="/" className="mr-1 flex-none text-sm font-bold tracking-tight">
            FPL<span className="text-emerald-600">Edge</span>
          </Link>
          {LINKS.map(([href, label]) => {
            const active = path === href;
            return (
              <Link
                key={href}
                href={href}
                className={`flex-none rounded-full px-2.5 py-1 text-[13px] font-medium ${
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
