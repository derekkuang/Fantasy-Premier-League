"use client";
// The conversational advisor.
//
// Deliberately NOT the way you ask "what's my best transfer?". That question is already
// answered deterministically at precompute time, for free, and is on the page above this one.
// Running an agent to recompute a cached answer would cost real money for something you can
// already read. What this is for is the follow-up the optimiser cannot express:
//
//     "…but I want to keep Haaland."     "what if I take a hit?"
//     "I'm saving for a wildcard."       "review my squad"
//
// Those are CONSTRAINTS. Supporting each one in the optimiser means a new parameter forever,
// because the space of things a manager says is open-ended while the space of operations is
// small and fixed. That asymmetry is the entire justification for the feature.
//
// Two things this component insists on. The starter chips solve the blank-page problem AND
// teach what the advisor is uniquely good at — an empty box invites "who's good this week",
// which is an expensive way to read the Predictions page. And when the backend says the
// advisor isn't configured, the section is absent: a feature that costs money per call must
// never look like it is working when it isn't, and its setup is not the visitor's business.

import { useEffect, useRef, useState } from "react";
import { API_URL } from "@/lib/api";

type Turn = { role: "user" | "assistant"; text: string; tools?: string[]; stub?: boolean };
type Status = { available: boolean; stub: boolean; model: string; reason: string | null };

const STARTERS = [
  "But I want to keep my captain",
  "What if I take a hit?",
  "I'm saving for a wildcard",
  "Review my squad",
];

export function AdvisorChat({
  gw,
  owned,
  bank,
  freeTransfers,
}: {
  gw: number;
  /** Explicit ids, so a squad built in the browser is advisable exactly like a fetched one. */
  owned: number[];
  bank: number;
  freeTransfers: number;
}) {
  const [status, setStatus] = useState<Status | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [history, setHistory] = useState<unknown[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let live = true;
    fetch(`${API_URL}/advise`)
      .then((r) => r.json())
      .then((s: Status) => live && setStatus(s))
      .catch(() => live && setStatus({ available: false, stub: false, model: "", reason: "The API is unreachable." }));
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [turns, busy]);

  async function send(text: string) {
    const message = text.trim();
    if (!message || busy) return;
    setDraft("");
    setError(null);
    setTurns((t) => [...t, { role: "user", text: message }]);
    setBusy(true);
    try {
      const res = await fetch(`${API_URL}/advise`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ gw, owned, bank, free_transfers: freeTransfers, message, history }),
      });
      const body = await res.json().catch(() => null);
      if (!res.ok) throw new Error(body?.detail ?? `Request failed (${res.status})`);
      setHistory(body.history ?? []);
      setTurns((t) => [
        ...t,
        {
          role: "assistant",
          text: body.reply,
          tools: (body.tool_calls ?? []).map((c: { tool: string }) => c.tool),
          stub: body.stub,
        },
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  // Nothing at all until the API says the advisor is on, and nothing while it is off. Users
  // were shown its setup instructions (an API key and a pip command) in its place, and the
  // starter chips flashed up before that. A feature that's switched off simply isn't there.
  if (!status || !status.available) return null;

  return (
    <div className="flex flex-col gap-1">
      <h2 className="t-label mb-1 flex items-baseline justify-between px-1 text-xs text-muted">
        <span>Ask about your squad</span>
        {status?.stub && (
          <span className="normal-case tracking-normal text-[var(--amber-fg)]">scripted preview</span>
        )}
      </h2>

      <div className="flex flex-col gap-2.5 rounded-2xl border border-black/10 p-3 dark:border-white/10">
        {status?.stub && (
          <p className="rounded-lg border border-[var(--amber-br)] bg-[var(--amber-bg)] px-2.5 py-2 text-[11px] leading-relaxed text-[var(--amber-fg)]">
            No API key configured, so the replies are scripted — but the tools behind them run
            for real, so every number below is genuine. This exists to test the interface, not
            the advice.
          </p>
        )}

        {turns.length === 0 && (
          <p className="text-[12px] leading-relaxed text-muted">
            The best transfer is already worked out above, for free. Use this for the part a
            calculator can&apos;t take: a constraint.
          </p>
        )}

        {turns.map((t, i) => (
          <div
            key={i}
            className={
              t.role === "user"
                ? "self-end rounded-2xl rounded-br-sm bg-emerald-600 px-3 py-2 text-[13px] text-white"
                : "rounded-2xl rounded-bl-sm border border-black/[.06] px-3 py-2 text-[13px] leading-relaxed dark:border-white/[.06]"
            }
          >
            {t.role === "assistant" ? <Markdownish text={t.text} /> : t.text}
            {t.tools && t.tools.length > 0 && (
              // Showing which tools ran is the structural honesty claim made visible: the
              // model cannot produce a number, it can only ask something else for one.
              <div className="mt-1.5 flex flex-wrap gap-1">
                {[...new Set(t.tools)].map((tool) => (
                  <span
                    key={tool}
                    className="rounded-full bg-black/[.06] px-2 py-0.5 font-mono text-[9px] text-muted dark:bg-white/10"
                  >
                    {tool}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}

        {busy && (
          <div className="rounded-2xl rounded-bl-sm border border-black/[.06] px-3 py-2 text-[13px] text-muted dark:border-white/[.06]">
            thinking…
          </div>
        )}
        {error && (
          <p className="rounded-lg border border-[var(--amber-br)] bg-[var(--amber-bg)] px-2.5 py-2 text-[12px] text-[var(--amber-fg)]">
            {error}
          </p>
        )}
        <div ref={endRef} />

        {turns.length === 0 && (
          <div className="flex flex-wrap gap-1.5">
            {STARTERS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => send(s)}
                disabled={busy}
                className="press min-h-8 rounded-full border border-black/10 px-3 py-1.5 text-[11px] font-medium hover:border-emerald-600 hover:text-emerald-600 disabled:opacity-40 dark:border-white/10"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(draft);
          }}
          className="flex gap-1.5"
        >
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="e.g. keep Salah, no hits"
            aria-label="Ask the advisor about your squad"
            maxLength={600}
            className="min-h-9 flex-1 rounded-full border border-black/15 bg-transparent px-3 py-1.5 text-[13px] outline-none ring-[var(--focus)] focus:ring-2 dark:border-white/15"
          />
          <button
            type="submit"
            disabled={busy || draft.trim() === ""}
            className="press min-h-9 flex-none rounded-full bg-emerald-600 px-4 text-[12px] font-semibold text-white disabled:opacity-40"
          >
            Ask
          </button>
        </form>
      </div>

      <p className="px-1 text-[12px] leading-relaxed text-muted">
        Every number it gives comes from the same calculations as the rest of the page. Limited
        to a few questions an hour.
      </p>
    </div>
  );
}

/** Just enough markdown for **bold** and paragraph breaks. A full parser is a dependency and
 *  an injection surface for something that renders model output. */
function Markdownish({ text }: { text: string }) {
  return (
    <>
      {text.split(/\n\n+/).map((para, i) => (
        <p key={i} className={i > 0 ? "mt-2" : ""}>
          {para.split(/(\*\*[^*]+\*\*)/g).map((chunk, j) =>
            chunk.startsWith("**") && chunk.endsWith("**") ? (
              <strong key={j} className="font-semibold">{chunk.slice(2, -2)}</strong>
            ) : (
              <span key={j}>{chunk}</span>
            ),
          )}
        </p>
      ))}
    </>
  );
}
