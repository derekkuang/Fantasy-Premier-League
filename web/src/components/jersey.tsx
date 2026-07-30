// A generic parametric football shirt, coloured per club. NOT an official kit — just a
// shirt silhouette filled with the club's primary/secondary colours (+ stripes / sash).
// Ported from the design's parametric SVG. Server-safe (no hooks): the body clip path is
// defined ONCE by <JerseyDefs/> at the top of the page and referenced by id here.

import type { KitPattern } from "@/lib/clubs";

const BODY =
  "M13 3 L17 3 Q20 8.5 23 3 L27 3 L28.5 12 L28.5 33 Q28.5 36 25.5 36 " +
  "L14.5 36 Q11.5 36 11.5 33 L11.5 12 Z";

/** Render once per page; every <Jersey/> references clip-path #jerseyBody. */
export function JerseyDefs() {
  return (
    <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden="true">
      <defs>
        <clipPath id="jerseyBody">
          <path d={BODY} />
        </clipPath>
      </defs>
    </svg>
  );
}

export function Jersey({
  primary,
  secondary,
  pattern = "solid",
  width,
  height,
  className = "",
}: {
  primary: string;
  secondary: string;
  pattern?: KitPattern;
  width: number;
  height: number;
  className?: string;
}) {
  return (
    <svg viewBox="0 0 40 38" width={width} height={height} role="img" aria-hidden="true" className={className}>
      {/* sleeves */}
      <path d="M13 3 L4.5 9 L6.5 20.5 L11.5 19.5 L11.5 3 Z" fill={secondary} />
      <path d="M27 3 L35.5 9 L33.5 20.5 L28.5 19.5 L28.5 3 Z" fill={secondary} />
      {/* body */}
      <path d={BODY} fill={primary} />
      {pattern === "stripes" && (
        <g fill={secondary} clipPath="url(#jerseyBody)">
          <rect x="12.6" y="3" width="2.8" height="33" />
          <rect x="18.6" y="3" width="2.8" height="33" />
          <rect x="24.6" y="3" width="2.8" height="33" />
        </g>
      )}
      {pattern === "sash" && (
        <path d="M11.5 31 L28.5 5 L28.5 13.5 L14.5 36 L11.5 36 Z" fill={secondary} clipPath="url(#jerseyBody)" />
      )}
      {/* collar + outline */}
      <path d="M16.4 2.4 L23.6 2.4 Q20 9.8 16.4 2.4 Z" fill={secondary} />
      <path d={BODY} fill="none" stroke="rgba(0,0,0,.28)" strokeWidth=".7" />
    </svg>
  );
}
