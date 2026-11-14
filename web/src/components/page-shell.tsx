// Shared shell for the content pages: a title and, at most, one line saying what the page is.

import type { ReactNode } from "react";

export function PageShell({ title, subtitle, children }: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <main className="mx-auto flex w-full min-w-0 max-w-5xl flex-1 flex-col gap-4 px-4 py-6">
      <div className="flex flex-col gap-1">
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
