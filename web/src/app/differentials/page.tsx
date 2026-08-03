import { getLatestGw, getPredictions } from "@/lib/api";
import { DifferentialsExplorer } from "@/components/differentials-view";
import { JerseyDefs } from "@/components/jersey";
import { PageError, PageShell } from "@/components/page-shell";

export default async function DifferentialsPage() {
  let data;
  try {
    data = await getPredictions(await getLatestGw());
  } catch (err) {
    return <PageError message={(err as Error).message} />;
  }
  return (
    <PageShell
      title="Differentials"
      subtitle="Players the field hasn't bought yet — ranked by what owning them gains you, never by how contrarian they are alone."
      meta={<span className="rounded-full bg-black/5 px-2 py-1 font-mono text-[11px] text-black/50 dark:bg-white/10 dark:text-white/50">{data.meta.model_ver}</span>}
    >
      {/* defines the #jerseyBody clip path every <Jersey/> references — render once */}
      <JerseyDefs />
      <DifferentialsExplorer predictions={data.predictions} />
      {/* page-specific model caveats only — affiliation, kits and the model disclaimer are
          in the global footer */}
      <p className="text-[11px] leading-relaxed text-black/55 dark:text-white/60">
        Ownership is FPL&apos;s overall <span className="font-mono">selected_by_percent</span> — a
        proxy for effective ownership, not top-10k and not captaincy-weighted. The risk band is
        derived from it, so it inherits that caveat. Promoted and low-data clubs are dropped from
        this ranking because their attacking shares aren&apos;t trustworthy yet.
      </p>
    </PageShell>
  );
}
