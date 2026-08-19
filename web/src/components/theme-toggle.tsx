"use client";
// Manual light/dark toggle. The initial theme is set pre-paint by the script in layout.tsx;
// this flips data-theme on <html> and remembers the choice in localStorage.
//
// WHY useSyncExternalStore RATHER THAN useState + useEffect. The theme genuinely lives on
// `<html data-theme>`, written before React ever runs. Mirroring it into component state inside
// an effect made React a second, lagging copy of a value something else owns: it cost an extra
// render on every mount, and React 19 flags it because a setState in an effect can cascade.
// Reading the DOM as an external store removes the copy — the observer re-renders us whenever
// the attribute changes, including if anything other than this button changes it.

import { useSyncExternalStore } from "react";

type Theme = "light" | "dark";

function subscribe(onChange: () => void) {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-theme"],
  });
  return () => observer.disconnect();
}

const getSnapshot = (): Theme =>
  document.documentElement.dataset.theme === "dark" ? "dark" : "light";

// null on the server: there is no DOM to read, and rendering nothing until mounted is what keeps
// the SSR and client markup identical.
const getServerSnapshot = (): Theme | null => null;

export function ThemeToggle() {
  const theme = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    // Write to the DOM only — the MutationObserver above turns that into a re-render, so there
    // is exactly one source of truth and no path where the two disagree.
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("theme", next);
    } catch {
      /* private mode / storage disabled — the toggle still works for this page view */
    }
  }

  return (
    <button
      type="button"
      onClick={toggle}
      title="Toggle light / dark"
      aria-label="Toggle light or dark theme"
      // 30px of ink, 46px of target: `.tap` grows the hit area without moving the layout.
      className="tap press grid h-[30px] w-[30px] flex-none place-items-center rounded-full border border-black/10 text-[13px] text-black/60 hover:border-emerald-600 hover:text-emerald-600 dark:border-white/10 dark:text-white/60"
    >
      {/* empty until mounted so SSR/CSR markup matches */}
      <span suppressHydrationWarning>{theme === null ? "" : theme === "dark" ? "☀" : "☾"}</span>
    </button>
  );
}
