// A row of mutually exclusive choices in one outlined pill: positions, fixture window and
// view, captain mode. One look for every mode switch on the site. Emerald stays for the page's
// main choice (the Players views) and for actions, so the two don't compete.

export function Segmented<T extends string | number>({ options, value, onChange, label, className = "" }: {
  options: readonly (readonly [T, string])[];
  value: T;
  onChange: (v: T) => void;
  /** What the group chooses, for screen readers: "Position", "Window". */
  label: string;
  className?: string;
}) {
  return (
    <div role="group" aria-label={label} className={`inline-flex max-w-full flex-none items-center overflow-x-auto rounded-full border border-[var(--line)] p-0.5 [scrollbar-width:none] ${className}`}>
      {options.map(([v, text]) => {
        const on = value === v;
        return (
          <button
            key={String(v)}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(v)}
            className={`press min-h-8 flex-none rounded-full px-3 text-[13px] font-semibold ${
              on ? "bg-[var(--chip-strong)] text-[var(--fg)]" : "text-muted hover:text-[var(--fg)]"
            }`}
          >
            {text}
          </button>
        );
      })}
    </div>
  );
}
