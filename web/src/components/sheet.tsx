"use client";
// The shell both sheets sit in: backdrop, panel, dismissal, and the modal behaviours that
// were missing from each of them separately.
//
// It was two near-identical copies before — same markup, same Escape handler, same
// `data-closing` wiring — which is how they came to differ in the details that matter and
// agree on the ones that don't. Extracting it also gives the modal semantics one home:
//
//   FOCUS      goes into the sheet on open and returns to whatever opened it on close.
//              Without that, dismissing drops a keyboard user back at the top of the
//              document, having lost the row they were reading.
//   TRAP       keeps Tab inside the panel while it is open, because everything behind it
//              is inert to a pointer and should be inert to a keyboard too.
//   SCROLL     locks the page underneath. A bottom sheet over a page that scrolls away
//              behind it makes the sheet look like it is sliding, not the page.
//   SEMANTICS  role="dialog" + aria-modal, so it is announced as a dialog rather than as
//              a pile of text that appeared.
//
// The drag lives in lib/use-sheet-drag.ts; here it is just wired to the panel.

import { useEffect, useRef, type ReactNode } from "react";
import { useDismissable } from "@/lib/use-dismissable";
import { useSheetDrag } from "@/lib/use-sheet-drag";

const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]),select,textarea,[tabindex]:not([tabindex="-1"])';

export function Sheet({
  onClose,
  label,
  className = "",
  children,
}: {
  onClose: () => void;
  /** Announced as the dialog's name — the player it is about, not "dialog". */
  label: string;
  /** Panel-level overrides: the desktop width and corner treatment differ per sheet. */
  className?: string;
  /** Receives `dismiss` so a close button inside the content animates out rather than
   *  unmounting the sheet from under its own exit transition. */
  children: (dismiss: () => void) => ReactNode;
}) {
  const { closing, dismiss } = useDismissable(onClose);
  const drag = useSheetDrag(dismiss);
  const restoreTo = useRef<HTMLElement | null>(null);

  // Remember the trigger before focus moves, then hand it back on the way out.
  useEffect(() => {
    restoreTo.current = document.activeElement as HTMLElement | null;
    const panel = drag.handlers.ref.current;
    // The panel itself, not the first control: a screen reader should read the header
    // before it reads the close button.
    panel?.focus({ preventScroll: true });
    return () => restoreTo.current?.focus?.({ preventScroll: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Lock the page behind it. Restoring the exact previous value rather than clearing it
  // matters if anything else ever locks too.
  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        dismiss();
        return;
      }
      if (e.key !== "Tab") return;
      const panel = drag.handlers.ref.current;
      if (!panel) return;
      const items = [...panel.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
        (el) => el.offsetParent !== null,
      );
      if (!items.length) {
        e.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      // Wrap at both ends, and catch the case where focus is on the panel itself.
      if (e.shiftKey && (document.activeElement === first || document.activeElement === panel)) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dismiss]);

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center">
      <div
        className="sheet-backdrop absolute inset-0 bg-black/45 backdrop-blur-[2px]"
        data-closing={closing}
        onClick={dismiss}
      />
      <div
        {...drag.handlers}
        role="dialog"
        aria-modal="true"
        aria-label={label}
        tabIndex={-1}
        data-closing={closing}
        data-dragging={drag.dragging}
        style={drag.style}
        className={
          "sheet-panel relative flex max-h-[88vh] w-full max-w-[430px] flex-col gap-3.5 " +
          "overflow-y-auto overscroll-contain rounded-t-[20px] border border-black/10 bg-white " +
          "px-4 pb-6 pt-2 shadow-[0_-8px_30px_rgba(0,0,0,.25)] focus:outline-none " +
          "dark:border-white/10 dark:bg-[#0a0a0a] " +
          className
        }
      >
        {/* Touch affordance for the drag, and the one band where the pull is guaranteed to
            reach us rather than being claimed by the scroll container. Hidden from
            assistive tech — Escape and the close button are the accessible paths. */}
        <div aria-hidden className="sheet-grip-area lg:hidden">
          <span className="sheet-grip" />
        </div>
        {children(dismiss)}
      </div>
    </div>
  );
}

/** The close control, identical in both sheets — 28px of ink, 44px of target. */
export function SheetClose({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      aria-label="Close"
      className="tap press grid h-7 w-7 flex-none place-items-center rounded-full border border-black/10 text-black/50 hover:text-black dark:border-white/10 dark:text-white/50 dark:hover:text-white"
    >
      ✕
    </button>
  );
}
