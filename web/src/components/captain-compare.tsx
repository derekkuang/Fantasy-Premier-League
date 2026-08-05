"use client";
// Captain card with a compare table. Two bases: "rank-adjusted" (differential value
// 2·xP·(1−EO), gated by an xP floor) and "raw xP". Mirrors the backend rank module; the
// chosen captain (passed in) drives the pitch armband and the doubled points.

import type { SquadPlayer } from "@/lib/api";
import { getClub } from "@/lib/clubs";
import { xpFloor } from "@/lib/formation";
import { Jersey } from "@/components/jersey";

/** Expected captain points you gain on a rival who does not own this player.
 *
 *  Unchanged maths — this is the backend's `captain_score`, 2·xP·(1−EO). What changed is
 *  that it is now labelled in the unit it was always in. Shown as `2xP(1−EO)` it read as a
 *  rival points total: a 6.2 xP differential scored 11.4 against Haaland's 6.4, which looks
 *  like the differential projects more points when he projects fewer. It doesn't — it
 *  projects more points *than the field gets*, which is a different and more useful thing,
 *  and saying so in points anchors it against the xP column beside it. */
const vsField = (p: SquadPlayer) => p.captain_score ?? 2 * p.xp * (1 - (p.ownership ?? 0) / 100);

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
  const candidates = [...starters]
    .sort((a, b) => (basis === "xp" ? b.xp - a.xp : vsField(b) - vsField(a)))
    .slice(0, 5);

  const Toggle = ({ id, label, hint }: { id: "rank" | "xp"; label: string; hint: string }) => (
    <button
      type="button"
      onClick={() => onBasis(id)}
      title={hint}
      className={`rounded-full border px-2.5 py-1 text-[10px] font-semibold ${
        basis === id
          ? "border-emerald-600 bg-emerald-600 text-white"
          : "border-black/10 text-black/55 dark:border-white/10 dark:text-white/55"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between px-0.5">
        <h2 className="t-label text-[11px] text-black/40 dark:text-white/40">
          Captain
        </h2>
        <div className="flex gap-1">
          <Toggle id="rank" label="rank-adjusted" hint="2·xP·(1−EO), gated by an xP floor" />
          <Toggle id="xp" label="raw xP" hint="highest raw xP" />
        </div>
      </div>

      <div className="flex flex-col gap-3 rounded-2xl border border-black/10 bg-white/70 p-4 shadow-sm dark:border-white/10 dark:bg-white/5">
        {pick && (() => {
          const club = getClub(pick.team);
          return (
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2.5">
                {/* The kit is how this player is identified everywhere else on the page —
                    the pitch, the bench, the sheet. Naming him in text alone made the one
                    card that names your captain the only place he had no face. */}
                <span className="relative flex-none">
                  <Jersey
                    primary={club.primary}
                    secondary={club.secondary}
                    pattern={club.pattern}
                    width={30}
                    height={28}
                    className="block"
                  />
                  <span className="absolute -right-1.5 -top-1 grid h-[15px] w-[15px] place-items-center rounded-full border-[1.5px] border-[var(--background)] bg-emerald-600 text-[9px] font-bold leading-none text-white">
                    C
                  </span>
                </span>
                <div className="flex flex-col">
                  <span className="t-title text-[15px] font-semibold">{pick.web_name}</span>
                  <span className="text-[11px] text-black/40 dark:text-white/40">
                    {pick.team} · {pick.ownership.toFixed(1)}% owned
                  </span>
                </div>
              </div>
              <div className="flex flex-none flex-col items-end">
                <span className="tabular-nums text-[13px] text-black/55 dark:text-white/55">
                  {pick.xp.toFixed(2)} xP × 2
                </span>
                <span className="tabular-nums text-[11px] text-emerald-600">
                  +{vsField(pick).toFixed(1)} pts vs field
                </span>
              </div>
            </div>
          );
        })()}

        <div className="flex flex-col gap-0.5 border-t border-black/[.06] pt-2.5 dark:border-white/[.06]">
          <div className="grid grid-cols-[1fr_38px_44px_62px] gap-1.5 px-1.5 pb-1 t-label text-[10px] text-black/40 dark:text-white/40">
            <span>candidate</span>
            <span className="text-right">xP</span>
            <span className="text-right">owned</span>
            <span className="text-right">vs field</span>
          </div>
          {candidates.map((c) => {
            const isPick = c.element_id === captainId;
            const belowFloor = basis === "rank" && c.xp < floor;
            const verdict = isPick ? "pick" : belowFloor ? "below xP floor" : "";
            const cc = getClub(c.team);
            return (
              <div
                key={c.element_id}
                className={`grid grid-cols-[1fr_38px_44px_62px] items-center gap-1.5 rounded-lg px-1.5 py-1 text-xs ${
                  isPick ? "bg-emerald-500/10" : ""
                }`}
              >
                <span className="flex min-w-0 items-center gap-1.5">
                  <Jersey
                    primary={cc.primary}
                    secondary={cc.secondary}
                    pattern={cc.pattern}
                    width={18}
                    height={17}
                    className="block flex-none"
                  />
                  <span className="flex min-w-0 flex-col">
                    <span className={`truncate ${isPick ? "font-semibold" : ""}`}>{c.web_name}</span>
                    {verdict && (
                      <span className={`text-[10px] ${isPick ? "text-emerald-600" : "text-black/35 dark:text-white/35"}`}>
                        {verdict}
                      </span>
                    )}
                  </span>
                </span>
                <span className="text-right tabular-nums text-black/55 dark:text-white/55">{c.xp.toFixed(1)}</span>
                <span className="text-right tabular-nums text-black/40 dark:text-white/40">{c.ownership.toFixed(0)}%</span>
                <span className={`text-right tabular-nums ${isPick ? "font-semibold text-emerald-600" : ""}`}>
                  +{vsField(c).toFixed(1)}
                </span>
              </div>
            );
          })}
          <p className="mt-1.5 px-1.5 text-[10px] leading-relaxed text-black/40 dark:text-white/40">
            <strong className="font-semibold">vs field</strong> = the captain points you expect to
            gain on a rival who doesn&apos;t own this player — 2 × xP × (1 − ownership). It is a
            margin, not a score: a differential can beat a premium here while projecting fewer
            points outright. Ownership is <em>selected&nbsp;by&nbsp;%</em>, a proxy for true
            effective ownership. Rank-adjusted ranks on this margin, gated by an xP floor of{" "}
            {floor.toFixed(1)} (80% of the best XI xP) so it can&apos;t pick a punt.
          </p>
        </div>
      </div>
    </div>
  );
}
