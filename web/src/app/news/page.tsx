// Team news: the latest stories for each club from public feeds, with FPL's own status beside
// every player named. Beta, and it changes no projection on the site. How well its keyword
// routing agrees with FPL is published on the model page rather than here.

import type { Metadata } from "next";
import { getNews, type NewsResponse } from "@/lib/api";
import { PageError, PageShell } from "@/components/page-shell";
import { Explained } from "@/components/explained";
import { NewsBoard } from "@/components/news-board";

export const metadata: Metadata = {
  title: "Team news — FPL Edge",
  description: "The latest team news for every Premier League club, from club sites, the BBC and the Guardian, with FPL's own status beside each player.",
  alternates: { canonical: "/news" },
};

export const revalidate = 900;

export default async function NewsPage() {
  let data: NewsResponse;
  try {
    data = await getNews();
  } catch {
    return <PageError message="Team news isn't available right now. It updates three times a day." />;
  }
  const updated = new Date(data.generated_at).toLocaleString("en-GB", {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "UTC",
  });

  return (
    <PageShell title="Team news" subtitle={`Latest from each club. Updated ${updated} UTC.`}>
      <Explained
        label="Where does this come from?"
        head={<span className="rounded-full bg-[var(--amber-bg)] px-2 py-0.5 text-[12px] font-semibold text-[var(--amber-fg)]">Beta</span>}
      >
        Stories come from each club&apos;s site, the Premier League, the BBC and the Guardian.
        Players named in a story show FPL&apos;s own status beside them, and FPL is the
        authority on availability. Nothing on this page changes a projection.
      </Explained>
      <NewsBoard clubs={Object.entries(data.clubs)} />
    </PageShell>
  );
}
