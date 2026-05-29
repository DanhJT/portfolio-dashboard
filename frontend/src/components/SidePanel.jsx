import React, { useState } from "react";

/**
 * Tabbed rail used on the right side of the dashboard. Renders the active
 * tab's content inside a bordered container with an internal scroll so the
 * overall page height stays predictable.
 *
 * Props:
 *   tabs: Array<{ key, label, count?, content: ReactNode }>
 *   initialKey: string (defaults to first tab)
 */
export default function SidePanel({ tabs, initialKey }) {
  const [active, setActive] = useState(initialKey ?? tabs[0]?.key);
  const activeTab = tabs.find((t) => t.key === active) ?? tabs[0];

  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-950 flex flex-col h-[640px] max-h-[calc(100vh-140px)]">
      <div
        role="tablist"
        className="flex border-b border-neutral-800 px-2 pt-2 gap-1"
      >
        {tabs.map((t) => {
          const isActive = t.key === active;
          return (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => setActive(t.key)}
              className={`flex items-center gap-1.5 rounded-t-md px-3 py-2 text-xs font-medium transition ${
                isActive
                  ? "bg-black text-white border border-neutral-800 border-b-transparent -mb-px"
                  : "text-neutral-400 hover:text-neutral-200"
              }`}
            >
              <span>{t.label}</span>
              {t.count !== undefined && (
                <span className="font-mono text-[10px] text-neutral-500">
                  {t.count}
                </span>
              )}
            </button>
          );
        })}
      </div>
      <div className="flex-1 overflow-y-auto p-4">{activeTab?.content}</div>
    </div>
  );
}
