"use client";
// The captain: one line with the pick, and "Compare captains" one tap away.
//
// Two ways to choose, which mirror the backend's rank module. "Most points" doubles whoever
// projects highest. "Beat rivals" doubles whoever gains you most on a rival who doesn't own
// him: 2 × xP × (1 − ownership), skipping anyone under an xP floor so it can't pick a punt. The
// table shows the edge column only in that mode, where it decides the pick; showing it in the
// other mode made the table look like it disagreed with its own choice.

import type { SquadPlayer } from "@/lib/api";
import { getClub } from "@/lib/clubs";
import { xpFloor } from "@/lib/formation";
import { Jersey } from "@/components/jersey";
import { Fold } from "@/components/fold";

/** Expected captain points you gain on a rival who doesn't own this player. */
const vsField = (p: SquadPlayer) => p.captain_score ?? 2 * p.xp * (1 - (p.ownership ?? 0) / 100);

const MODES: { id: "xp" | "rank"; label: string }[] = [
  { id: "xp", label: "Most points" },
  { id: "rank", label: "Beat rivals" },
];

export function CaptainCompare({
  starters,
  basis,
  onBasis,
  captainId,
}: {
  starters: SquadPlayer[];
  basis: "rank" | "xp";
  onBasis: (b: "rank" | "xp") => void;
  captainId: number | null;
}) {
  const floor = xpFloor(starters);
  const pick = starters.find((p) => p.element_id === captainId) ?? null;
  const rank = basis === "rank";
  const candidates = [...starters].sort((a, b) => (rank ? vsField(b) - vsField(a) : b.xp - a.xp)).slice(0, 5);
  const club = pick ? getClub(pick.team) : null;

  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-[13px] font-semibold text-muted">Captain</h2>
      <div className="flex flex-col rounded-2xl border border-[var(--line)] px-4 pt-3">
        {pick && club && (
          <div className="flex items-center justify-between gap-3 pb-3">
            <div className="flex min-w-0 items-center gap-3">
              <span className="relative flex-none">
                <Jersey primary={club.primary} secondary={club.secondary} pattern={club.pattern} width={30} height={28} className="block" />
                <span className="absolute -right-1.5 -top-1 grid h-[15px] w-[15px] place-items-center rounded-full border-[1.5px] border-[var(--background)] bg-emerald-600 text-[9px] font-bold leading-none text-white">
                  C
                </span>
              </span>
              <span className="flex min-w-0 flex-col">
                <span className="t-title truncate text-[16px] font-semibold">{pick.web_name}</span>
                <span className="text-[12px] text-muted">{pick.team} · {pick.ownership.toFixed(0)}% owned</span>
              </span>
            </div>
            <span className="flex-none text-[15px] font-bold tabular-nums">
              {pick.xp.toFixed(1)} <span className="text-[13px] font-normal text-muted">xP × 2</span>
            </span>
          </div>
        )}

        <Fold title="Compare captains" aside={MODES.find((m) => m.id === basis)?.label}>
          <div className="flex flex-col gap-2.5">
            <div className="flex gap-1.5" role="group" aria-label="How to choose the captain">
              {MODES.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => onBasis(m.id)}
                  aria-pressed={basis === m.id}
                  className={`press rounded-full border px-3 py-1.5 text-[13px] font-semibold ${
                    basis === m.id ? "border-emerald-600 bg-emerald-600 text-white" : "border-[var(--line)] text-muted"
                  }`}
                >
                  {m.label}
                </button>
              ))}
            </div>
            <p className="text-[12px] leading-relaxed text-muted">
              {rank
                ? `Doubles whoever gains you most on a rival who doesn't own him: twice his xP times the share of managers without him. Anyone under ${floor.toFixed(1)} xP is skipped, so it can't pick a punt.`
                : "Doubles whoever projects the most points."}
            </p>
            <table className="w-full text-[13px] tabular-nums">
              <thead>
                <tr className="text-[12px] text-muted">
                  <th className="py-1 text-left font-normal">Player</th>
                  <th className="py-1 text-right font-normal">xP</th>
                  <th className="py-1 text-right font-normal">Owned</th>
                  {rank && <th className="py-1 text-right font-normal">Edge</th>}
                </tr>
              </thead>
              <tbody>
                {candidates.map((c) => {
                  const isPick = c.element_id === captainId;
                  const below = rank && c.xp < floor;
                  return (
                    <tr key={c.element_id} className={`border-t border-[var(--line)] ${isPick ? "font-semibold" : ""}`}>
                      <td className="py-1.5">
                        {c.web_name}
                        {isPick && <span className="ml-1.5 text-[12px] text-[var(--emerald-text)]">captain</span>}
                        {below && !isPick && <span className="ml-1.5 text-[12px] font-normal text-muted">under the floor</span>}
                      </td>
                      <td className="py-1.5 text-right">{c.xp.toFixed(1)}</td>
                      <td className="py-1.5 text-right">{c.ownership.toFixed(0)}%</td>
                      {rank && <td className="py-1.5 text-right">+{vsField(c).toFixed(1)}</td>}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Fold>
      </div>
    </section>
  );
}
