"use client";
// Deferred unmount, so a dismissable surface can animate on the way OUT.
//
// `{open && <Sheet/>}` removes the element from the DOM the instant it closes, and an element
// that isn't there cannot transition. So the close path is: mark it closing (CSS drives the
// exit off `data-closing`), wait for the transition, then actually unmount. Entry needs none of
// this — `@starting-style` handles it with no JS at all.
//
// Symmetry is the point. A sheet that slides up and then vanishes reads as a glitch; it has to
// leave the way it arrived.

import { useCallback, useEffect, useRef, useState } from "react";

/** Matches --dur-sheet in globals.css. Keep the two in step. */
export const SHEET_EXIT_MS = 400;

export function useDismissable(onClose: () => void, ms: number = SHEET_EXIT_MS) {
  const [closing, setClosing] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  const dismiss = useCallback(() => {
    if (timer.current) return;   // already on the way out — ignore repeat presses
    // Someone who has asked for less motion should not also be made to wait for it.
    const reduced =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      onClose();
      return;
    }
    setClosing(true);
    timer.current = setTimeout(onClose, ms);
  }, [onClose, ms]);

  return { closing, dismiss };
}
