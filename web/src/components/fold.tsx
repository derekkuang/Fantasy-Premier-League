// A section that opens on tap. The site's rule for detail: the answer stays on screen, and the
// working (breakdowns, methods, tables) sits one tap away under a title that says what's inside
// and, where it helps, a short summary on the right so most people never need to open it.
//
// A native <details>, so it works without JavaScript, is keyboard-operable for free, and the
// browser's find-in-page opens it when a match is inside.

import type { ReactNode } from "react";

export function Fold({
  title,
  aside,
  children,
  defaultOpen = false,
  className = "",
}: {
  title: ReactNode;
  /** A one-line summary shown beside the title, e.g. "71.0 predicted · 70 scored". */
  aside?: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  className?: string;
}) {
  return (
    <details className={`fold border-t border-[var(--line)] ${className}`} open={defaultOpen}>
      <summary className="press flex min-h-11 cursor-pointer items-center justify-between gap-3 py-2.5">
        <span className="text-[14px] font-semibold">{title}</span>
        <span className="flex min-w-0 items-center gap-2 text-[13px] text-muted">
          {aside != null && <span className="truncate tabular-nums">{aside}</span>}
          <svg aria-hidden className="chev flex-none" width="8" height="12" viewBox="0 0 8 12">
            <path d="M1.5 1.5 6 6l-4.5 4.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
      </summary>
      <div className="pb-4">{children}</div>
    </details>
  );
}
