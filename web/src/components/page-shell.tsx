// Shared shell for the free content pages (fixtures / predictions / differentials).

import type { ReactNode } from "react";

export function PageShell({ title, subtitle, meta, children }: {
  title: string;
  subtitle?: string;
  meta?: ReactNode;
  children: ReactNode;
}) {
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-4 px-4 py-6">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h1 className="t-title text-xl font-bold">{title}</h1>
          {subtitle && <p className="mt-0.5 text-sm text-black/50 dark:text-white/50">{subtitle}</p>}
        </div>
        {meta}
      </div>
      {children}
    </main>
  );
}

export function PageError({ message }: { message: string }) {
  return (
    <PageShell title="Couldn't load this yet">
      <p className="text-sm text-black/60 dark:text-white/60">{message}</p>
      <p className="text-xs text-black/40 dark:text-white/40">
        This gameweek may not be precomputed yet — try again shortly.
      </p>
    </PageShell>
  );
}
