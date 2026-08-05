"use client";
// Drag-to-dismiss for the mobile bottom sheet.
//
// The sheet was dismissable only by hitting a 28px ✕ or the backdrop behind it. On a phone
// the sheet covers most of the screen and the thumb is nowhere near either. Pulling it down
// is the gesture people already try, and it is the one interaction in this app where direct
// manipulation genuinely belongs: the sheet should be a thing you push around, not a thing
// that plays an animation at you.
//
// Four properties make it feel like an object rather than a slider:
//
//   1:1 TRACKING     — it moves exactly as far as the finger, offset from where it was
//                      grabbed, for the whole gesture. Pointer capture keeps that true
//                      after the finger leaves the element's bounds.
//   RESISTANCE       — dragging UP has nowhere to go, so it resists progressively instead
//                      of stopping dead. A hard stop reads as frozen; resistance reads as
//                      "responsive, but there is nothing more here".
//   MOMENTUM         — release is judged on where the flick was GOING, not where it let
//                      go. A short fast flick dismisses; a long slow drag that stopped
//                      short does not. Same projection curve as scroll deceleration.
//   INTERRUPTIBILITY — grabbing a sheet that is springing back picks it up from where it
//                      visually IS, not from where it logically was. Reading the live
//                      matrix is what stops the jump.
//
// Only for touch: a mouse has the ✕ and the backdrop and doesn't need to drag a dialog.
// It also stands down when the sheet's own content is scrolled, so pulling down inside a
// scrolled sheet scrolls it back to the top first — the sheet only moves from the top.

import { useCallback, useRef, useState } from "react";

/** Past this projected travel, release dismisses instead of springing back. */
const DISMISS_PX = 88;
/** Or this fast, regardless of distance — a decisive flick shouldn't need the distance. */
const DISMISS_VELOCITY = 550;
/** Matches scroll deceleration. Higher = a flick carries further. */
const DECELERATION = 0.998;
/** Samples kept for the velocity estimate; more would average away the final flick. */
const SAMPLES = 5;

/** Where a flick would come to rest. Exponential decay — NOT the v²/2a from physics class,
 *  which decelerates far too abruptly to match how a thrown surface reads. */
function project(velocity: number, rate = DECELERATION): number {
  return (velocity / 1000) * rate / (1 - rate);
}

/** Progressive resistance past a bound: the further you pull, the less it follows. */
function rubberband(overshoot: number, dimension: number, c = 0.55): number {
  return (overshoot * dimension * c) / (dimension + c * Math.abs(overshoot));
}

/** The element's live on-screen translateY, mid-transition. Starting a new gesture from
 *  the target value instead of this one is what produces a visible jump on interrupt. */
function currentTranslateY(el: HTMLElement): number {
  const t = getComputedStyle(el).transform;
  if (!t || t === "none") return 0;
  const m = new DOMMatrixReadOnly(t);
  return m.m42;
}

export function useSheetDrag(dismiss: () => void) {
  const [dragY, setDragY] = useState(0);
  const [dragging, setDragging] = useState(false);

  const panel = useRef<HTMLDivElement | null>(null);
  const startY = useRef(0);
  const base = useRef(0);
  const samples = useRef<{ y: number; t: number }[]>([]);
  const active = useRef(false);

  const onPointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    const el = panel.current;
    if (!el) return;
    // Fine pointers get the close button and the backdrop; they don't need to drag a dialog.
    if (e.pointerType === "mouse") return;
    // The panel scrolls. A downward pull from a scrolled position belongs to the content.
    if (el.scrollTop > 0) return;

    active.current = true;
    // Pick the sheet up from where it visually is, so grabbing one in flight doesn't jump.
    base.current = dragging ? dragY : currentTranslateY(el);
    startY.current = e.clientY;
    samples.current = [{ y: e.clientY, t: e.timeStamp }];
    setDragY(base.current);
    setDragging(true);
    el.setPointerCapture(e.pointerId);
  }, [dragY, dragging]);

  const onPointerMove = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if (!active.current) return;
    const el = panel.current;
    if (!el) return;

    const raw = base.current + (e.clientY - startY.current);
    const height = el.offsetHeight || 1;
    // Down is free; up is bounded by the sheet's own top edge, so it resists.
    setDragY(raw >= 0 ? raw : -rubberband(-raw, height));

    samples.current.push({ y: e.clientY, t: e.timeStamp });
    if (samples.current.length > SAMPLES) samples.current.shift();
  }, []);

  const end = useCallback(() => {
    if (!active.current) return;
    active.current = false;
    setDragging(false);

    // Velocity across the retained window, in px/s. Two samples at the same timestamp
    // (which coalesced pointer events can produce) would divide by zero.
    const s = samples.current;
    const first = s[0];
    const last = s[s.length - 1];
    const dt = last && first ? last.t - first.t : 0;
    const velocity = dt > 0 ? ((last.y - first.y) / dt) * 1000 : 0;

    setDragY((y) => {
      const projected = y + project(velocity);
      if (velocity > DISMISS_VELOCITY || projected > DISMISS_PX) {
        dismiss();
        return y;   // leave it where it is; the exit transition takes it the rest of the way
      }
      return 0;     // under the bar — the CSS transition springs it home
    });
  }, [dismiss]);

  return {
    /** Spread onto the scrolling panel element. */
    handlers: {
      ref: panel,
      onPointerDown,
      onPointerMove,
      onPointerUp: end,
      onPointerCancel: end,
    },
    /** Inline transform while dragging; `undefined` hands control back to CSS. */
    style: dragging ? { transform: `translateY(${dragY}px)` } : undefined,
    dragging,
  };
}
