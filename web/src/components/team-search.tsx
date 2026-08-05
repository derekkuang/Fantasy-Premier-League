"use client";
// A Client Component: the "use client" directive at the top means this runs in the
// browser, so it can hold state (the typed id) and respond to events. This is the ONE
// interactive island on the home page — everything else stays a Server Component.

import { useRouter } from "next/navigation";
import { useState } from "react";

export function TeamSearch({ collapsible = false }: { collapsible?: boolean }) {
  const [id, setId] = useState("");            // the FPL team id the user types
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(!collapsible);
  const router = useRouter();

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = id.trim();
    if (!/^\d+$/.test(trimmed)) return;        // ids are numeric
    setBusy(true);
    router.push(`/team/${trimmed}`);           // navigate to the dynamic route
  }

  // Secondary path, folded away until asked for. Most arrivals don't have their id to
  // hand — and before the first deadline the FPL API serves no squads at all, so this
  // route 404s for everyone. It shouldn't be the first thing anyone is asked to do.
  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="press text-center text-sm text-black/50 hover:text-emerald-600 dark:text-white/50"
      >
        Already know your FPL team ID? <span className="underline">Paste it instead</span>
      </button>
    );
  }

  return (
    <form onSubmit={onSubmit} className="flex w-full flex-col gap-3 sm:flex-row">
      <input
        inputMode="numeric"
        value={id}
        onChange={(e) => setId(e.target.value)}
        placeholder="Your FPL team ID (e.g. 1234567)"
        className="flex-1 rounded-xl border border-black/15 bg-white px-4 py-3 text-base outline-none
                   ring-[var(--focus)] focus:ring-2 dark:border-white/15 dark:bg-white/5"
      />
      <button
        type="submit"
        disabled={busy || id.trim() === ""}
        className="press rounded-xl bg-emerald-600 px-5 py-3 font-semibold text-white
                   hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {busy ? "Loading…" : "Get my GW plan"}
      </button>
    </form>
  );
}
