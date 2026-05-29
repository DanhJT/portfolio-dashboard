import React from "react";

export default function TabNav({ tabs, active, onChange }) {
  return (
    <div className="border-b border-neutral-900 bg-black">
      <div className="mx-auto max-w-[1600px] px-6 flex gap-1 overflow-x-auto">
        {tabs.map((t) => {
          const isActive = t.key === active;
          return (
            <button
              key={t.key}
              type="button"
              onClick={() => onChange(t.key)}
              className={`px-4 py-3 text-sm font-medium whitespace-nowrap transition border-b-2 ${
                isActive
                  ? "border-white text-white"
                  : "border-transparent text-neutral-400 hover:text-neutral-200"
              }`}
            >
              {t.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
