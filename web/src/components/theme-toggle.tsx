"use client";
// Manual light/dark toggle. The initial theme is set pre-paint by the script in layout.tsx;
// this just flips data-theme on <html> and remembers the choice in localStorage.

import { useEffect, useState } from "react";

export function ThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark" | null>(null);

  useEffect(() => {
    setTheme((document.documentElement.dataset.theme as "light" | "dark") ?? "light");
  }, []);

  function toggle() {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("theme", next);
    } catch {
      /* ignore */
    }
    setTheme(next);
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
