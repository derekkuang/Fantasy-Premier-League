// Team news, availability first (HANDOFF §39): FPL's own list of doubtful, injured and
// suspended players, then the last week's team news (injuries, suspensions, returns, line-ups,
// press conferences and manager changes at first teams). Everything else a club publishes,
// from the mascot to the shop, is left out when the digest is built. Beta; it changes no
// projection.

import type { Metadata } from "next";
import { getNews, type NewsResponse } from "@/lib/api";
import { PageError, PageShell } from "@/components/page-shell";
import { Explained } from "@/components/explained";
import { JerseyDefs } from "@/components/jersey";
import { NewsBoard, type Story } from "@/components/news-board";

export const metadata: Metadata = {
  title: "Team news — FPL Edge",
  description: "Every Premier League player FPL has flagged as doubtful, injured or suspended, and the week's team news: injuries, returns, line-ups and manager changes.",
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
  // Only stories the team-news filter labelled. A digest from before the filter carries none,
  // so the page shows an empty week rather than the unfiltered feed.
  const stories: Story[] = Object.entries(data.clubs)
    .flatMap(([club, items]) => items.filter((it) => it.labels?.length).map((it) => ({ ...it, club })))
    .sort((a, b) => (Date.parse(b.published ?? "") || 0) - (Date.parse(a.published ?? "") || 0));

  return (
    <PageShell narrow title="Team news" subtitle={`Injuries, suspensions and the week's team news. Updated ${updated} UTC.`}>
      <JerseyDefs />
      <Explained
        label="Where does this come from?"
        head={<span className="rounded-full bg-[var(--amber-bg)] px-2 py-0.5 text-[12px] font-semibold text-[var(--amber-fg)]">Beta</span>}
      >
        {"The injury list is FPL's own: everyone it marks doubtful, injured or suspended, in its words. " +
          "Stories come from club sites, the Premier League, the BBC and the Guardian, and stay only when the " +
          "headline is about an injury, suspension, return, line-up, press conference or manager change at a " +
          "first team. Nothing here changes a projection."}
      </Explained>
      <NewsBoard flagged={data.flagged ?? []} stories={stories} generatedAt={data.generated_at} windowDays={data.window_days ?? 7} />
    </PageShell>
  );
}
