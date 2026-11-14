// Shared shell for the content pages: a title and, at most, one line saying what the page is.

import Link from "next/link";
import type { ReactNode } from "react";

export function PageShell({ title, subtitle, narrow = false, back, children }: {
  title: string;
  subtitle?: string;
  /** Pages people read (news, the model) at a reading width; tables and grids use the full one. */
  narrow?: boolean;
  /** A page inside a tab (one match, inside Fixtures) links back to it. */
  back?: { href: string; label: string };
  children: ReactNode;
}) {
  return (
    <main className={`mx-auto flex w-full min-w-0 flex-1 flex-col gap-4 px-4 py-6 ${narrow ? "max-w-3xl" : "max-w-5xl"}`}>
      <div className="flex flex-col gap-1">
        {back && (
          <Link href={back.href} className="press -ml-1 mb-1 self-start rounded-full px-1 py-0.5 text-[13px] font-semibold text-muted hover:text-[var(--emerald-text)]">
            {`← ${back.label}`}
          </Link>
        )}
        <h1 className="t-title text-[22px] font-bold">{title}</h1>
        {subtitle && <p className="text-[14px] text-muted">{subtitle}</p>}
      </div>
      {children}
    </main>
  );
}

export function PageError({ message }: { message: string }) {
  return (
    <PageShell title="Couldn't load this yet">
      <p className="text-[14px] text-muted">{message}</p>
    </PageShell>
  );
}
