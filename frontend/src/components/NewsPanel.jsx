import React, { useMemo, useState } from "react";

const ALL = "__all__";

function relativeTime(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)}d ago`;
  return d.toLocaleDateString();
}

function FilterChip({ label, count, active, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition ${
        active
          ? "border-white bg-white text-black"
          : "border-neutral-800 bg-black text-neutral-300 hover:bg-neutral-900"
      }`}
      aria-pressed={active}
    >
      <span>{label}</span>
      {count !== undefined && (
        <span
          className={`font-mono ${
            active ? "text-neutral-500" : "text-neutral-500"
          }`}
        >
          {count}
        </span>
      )}
    </button>
  );
}

export default function NewsPanel({ news, loading, tickers = [] }) {
  const [filter, setFilter] = useState(ALL);

  const items = news?.items ?? [];

  const countsByTicker = useMemo(() => {
    const m = new Map();
    for (const it of items) {
      m.set(it.ticker, (m.get(it.ticker) ?? 0) + 1);
    }
    return m;
  }, [items]);

  const filtered = useMemo(() => {
    if (filter === ALL) return items;
    return items.filter((it) => it.ticker === filter);
  }, [items, filter]);

  return (
    <div>
      <div className="flex items-baseline justify-between mb-3">
        <span className="text-xs text-neutral-500">
          {loading
            ? "Loading…"
            : `${filtered.length} of ${items.length} stories`}
        </span>
      </div>

      {tickers.length > 0 && items.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-4">
          <FilterChip
            label="All"
            count={items.length}
            active={filter === ALL}
            onClick={() => setFilter(ALL)}
          />
          {tickers.map((t) => (
            <FilterChip
              key={t}
              label={t}
              count={countsByTicker.get(t) ?? 0}
              active={filter === t}
              onClick={() => setFilter(t)}
            />
          ))}
        </div>
      )}

      {!loading && filtered.length === 0 && (
        <div className="text-sm text-neutral-500">
          {filter === ALL
            ? "No recent news available for the current holdings."
            : `No recent news for ${filter}.`}
        </div>
      )}

      <ul className="divide-y divide-neutral-900">
        {filtered.map((item, i) => (
          <li key={`${item.ticker}-${i}`} className="py-2 first:pt-0 last:pb-0">
            <div className="flex items-start gap-2">
              <span className="shrink-0 mt-0.5 inline-flex items-center rounded border border-neutral-800 px-1.5 py-0.5 text-[10px] font-mono uppercase tracking-wider text-neutral-300">
                {item.ticker}
              </span>
              <div className="min-w-0 flex-1">
                {item.url ? (
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block text-[13px] leading-snug text-white hover:underline line-clamp-2"
                  >
                    {item.title}
                  </a>
                ) : (
                  <div className="text-[13px] leading-snug text-white line-clamp-2">
                    {item.title}
                  </div>
                )}
                <div className="mt-0.5 text-[11px] text-neutral-500 flex items-center gap-1.5 truncate">
                  {item.publisher && <span className="truncate">{item.publisher}</span>}
                  {item.publisher && item.published_at && (
                    <span aria-hidden>·</span>
                  )}
                  {item.published_at && (
                    <span className="shrink-0">{relativeTime(item.published_at)}</span>
                  )}
                </div>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
