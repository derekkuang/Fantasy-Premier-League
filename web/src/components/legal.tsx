// Shared shell + typography for the legal pages, so Privacy and Terms read identically and
// neither drifts into its own styling.

import type { ReactNode } from "react";

export function LegalPage({ title, updated, children }: {
  title: string;
  updated: string;
  children: ReactNode;
}) {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-5 px-4 py-8">
      <div className="flex flex-col gap-1">
        <h1 className="t-title text-xl font-bold">{title}</h1>
        <p className="text-[11px] text-black/55 dark:text-white/60">Last updated {updated}</p>
      </div>
      <div className="flex flex-col gap-5">{children}</div>
    </main>
  );
}

export function S({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="t-label text-[13px] text-black/55 dark:text-white/60">
        {title}
      </h2>
      {children}
    </section>
  );
}

export function P({ children }: { children: ReactNode }) {
  return (
    <p className="max-w-[68ch] text-[13px] leading-relaxed text-black/70 dark:text-white/70">
      {children}
    </p>
  );
}
