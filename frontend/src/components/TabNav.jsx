import React from "react";

// Inline tabs for the single header bar. Stretches to the bar's full height so
// the active underline sits flush with the header's bottom border.
export default function TabNav({ tabs, active, onChange }) {
  return (
    <nav className="flex gap-1 overflow-x-auto self-stretch">
      {tabs.map((t) => {
        const isActive = t.key === active;
        return (
          <button
            key={t.key}
            type="button"
            onClick={() => onChange(t.key)}
            className={`h-full px-3 text-xs font-medium whitespace-nowrap transition border-b-2 ${
              isActive
                ? "border-white text-white bg-chassis-high"
                : "border-transparent text-neutral-400 hover:text-neutral-200"
            }`}
          >
            {t.label}
          </button>
        );
      })}
    </nav>
  );
}
