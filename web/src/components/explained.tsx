"use client";
// A heading with a small "i" beside it that opens one sentence underneath. For the definitions
// that used to sit on the page as paragraphs: the term stays on screen, its explanation is one
// tap away, and nobody who already knows it has to read it again.

import { useId, useState, type ReactNode } from "react";

export function Explained({ head, label, children, className = "" }: {
  head: ReactNode;
  /** What the button says to a screen reader, e.g. "What is edge?" */
  label: string;
  children: ReactNode;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <div className={`flex flex-col gap-1.5 ${className}`}>
      <div className="flex items-center gap-2">
        {head}
        <button
          type="button"
          aria-label={label}
          title={label}
          aria-expanded={open}
          aria-controls={id}
          onClick={() => setOpen((o) => !o)}
          className={`press tap grid h-5 w-5 flex-none place-items-center rounded-full border text-[11px] font-semibold ${
            open ? "border-emerald-600 text-[var(--emerald-text)]" : "border-[var(--line)] text-muted"
          }`}
        >
          i
        </button>
      </div>
      {open && (
        <p id={id} className="max-w-[62ch] text-[12px] leading-relaxed text-muted">
          {children}
        </p>
      )}
    </div>
  );
}
