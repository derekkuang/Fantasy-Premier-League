"use client";
// Four destinations: My team, Players, Fixtures, News. The model page lives in the footer.
//
// Six links didn't fit a phone: three sat off-screen in a sideways-scrolling strip with nothing
// to say they were there. Now phones get a tab bar along the bottom (the four always visible,
// in thumb reach) and the top bar keeps only the name and the theme switch. Wider screens get
// the four links in the top bar.

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { ThemeToggle } from "@/components/theme-toggle";

type Tab = { href: string; label: string; match: (p: string) => boolean; icon: ReactNode };

const stroke = { fill: "none", stroke: "currentColor", strokeWidth: 1.7, strokeLinecap: "round", strokeLinejoin: "round" } as const;

const TABS: Tab[] = [
  {
    href: "/squad", label: "My team",
    match: (p) => p.startsWith("/squad") || p.startsWith("/team"),
    icon: <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden><path {...stroke} d="M8 3 4 5.5 2.5 10l3 1.2V21h13v-9.8l3-1.2L20 5.5 16 3c-.6 1.6-2.2 2.6-4 2.6S8.6 4.6 8 3Z" /></svg>,
  },
  {
    href: "/players", label: "Players",
    match: (p) => p.startsWith("/players"),
    icon: <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden><path {...stroke} d="M9 6h11M9 12h11M9 18h11" /><circle cx="4.5" cy="6" r="1.3" fill="currentColor" /><circle cx="4.5" cy="12" r="1.3" fill="currentColor" /><circle cx="4.5" cy="18" r="1.3" fill="currentColor" /></svg>,
  },
  {
    href: "/fixtures", label: "Fixtures",
    match: (p) => p.startsWith("/fixtures"),
    icon: <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden><rect {...stroke} x="3.5" y="5" width="17" height="15.5" rx="2.5" /><path {...stroke} d="M3.5 10h17M8 3v4M16 3v4" /></svg>,
  },
  {
    href: "/news", label: "News",
    match: (p) => p.startsWith("/news"),
    icon: <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden><path {...stroke} d="M5 4.5h11.5v15H6.5A1.5 1.5 0 0 1 5 18V4.5Z" /><path {...stroke} d="M16.5 8.5H19v9.5a1.5 1.5 0 0 1-3 0M8 8.5h5.5M8 12h5.5M8 15.5h3.5" /></svg>,
  },
];

export function Nav() {
  const path = usePathname();
  return (
    <>
      <nav aria-label="Main" className="chrome chrome-edge sticky top-0 z-30 h-[var(--nav-h)]">
        <div className="mx-auto flex h-full max-w-5xl items-center justify-between gap-2 px-4">
          <div className="flex items-center gap-1">
            <Link href="/" className="press t-title mr-2 flex-none text-[15px] font-bold">
              FPL<span className="text-emerald-600">Edge</span>
            </Link>
            {TABS.map((t) => {
              const active = t.match(path);
              return (
                <Link
                  key={t.href}
                  href={t.href}
                  aria-current={active ? "page" : undefined}
                  className={`press hidden flex-none rounded-full px-3 py-1.5 text-[14px] font-medium md:block ${
                    active ? "bg-emerald-600 text-white" : "text-muted hover:text-[var(--fg)]"
                  }`}
                >
                  {t.label}
                </Link>
              );
            })}
          </div>
          <ThemeToggle />
        </div>
      </nav>

      {/* phones: the tab bar */}
      <nav
        aria-label="Main"
        className="chrome fixed inset-x-0 bottom-0 z-40 border-t border-[var(--line)] pb-[env(safe-area-inset-bottom,0px)] md:hidden"
      >
        <div className="mx-auto grid h-14 max-w-md grid-cols-4">
          {TABS.map((t) => {
            const active = t.match(path);
            return (
              <Link
                key={t.href}
                href={t.href}
                aria-current={active ? "page" : undefined}
                className={`press flex flex-col items-center justify-center gap-0.5 text-[11px] font-semibold ${
                  active ? "text-[var(--emerald-text)]" : "text-muted"
                }`}
              >
                {t.icon}
                {t.label}
              </Link>
            );
          })}
        </div>
      </nav>
    </>
  );
}
