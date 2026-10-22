import React, { useEffect, useMemo, useState } from "react";

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

function selectionLabel(selected, tickers) {
  if (selected.size === 0) return "All stocks";
  if (selected.size > 2) return `${selected.size} stocks`;
  // Portfolio order, not click order, so the label doesn't reshuffle.
  return tickers.filter((t) => selected.has(t)).join(", ");
}

export default function NewsPanel({ news, loading, tickers = [] }) {
  // Tickers whose news is shown. Empty means All, which is the default.
  const [selected, setSelected] = useState(() => new Set());
  const [open, setOpen] = useState(false);

  const items = news?.items ?? [];

  const countsByTicker = useMemo(() => {
    const m = new Map();
    for (const it of items) {
      m.set(it.ticker, (m.get(it.ticker) ?? 0) + 1);
    }
    return m;
  }, [items]);

  const filtered = useMemo(() => {
    if (selected.size === 0) return items;
    return items.filter((it) => selected.has(it.ticker));
  }, [items, selected]);

  // A rebalance can drop selected holdings out of the portfolio; forget those
  // and keep the rest. If none are left the filter is back to All.
  useEffect(() => {
    setSelected((prev) => {
      const kept = [...prev].filter((t) => tickers.includes(t));
      return kept.length === prev.size ? prev : new Set(kept);
    });
  }, [tickers]);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  const toggle = (t) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });
  };

  const clear = () => setSelected(new Set());

  const showFilter = tickers.length > 0 && items.length > 0;

  return (
    <div>
      <div className="flex items-baseline justify-between gap-2 mb-3">
        <span className="text-xs text-neutral-500">
          {loading
            ? "Loading…"
            : `${filtered.length} of ${items.length} stories`}
        </span>

        {showFilter && (
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            aria-expanded={open}
            aria-controls="news-filter"
            className="control control-hover shrink-0 max-w-[60%] truncate px-2 py-1 text-xs font-mono text-neutral-200"
          >
            {selectionLabel(selected, tickers)}
            <span aria-hidden className="ml-1.5 text-neutral-500">
              {open ? "▴" : "▾"}
            </span>
          </button>
        )}
      </div>

      {/* Rendered in flow rather than as a floating menu: this panel scrolls,
          and a 15-row overlay would be clipped by its edge. */}
      {showFilter && open && (
        <div id="news-filter" className="panel-raise p-2 mb-3">
          <div className="flex items-center justify-between gap-2 mb-2 pb-2 border-b rule">
            <label className="inline-flex items-center gap-1.5 text-xs text-neutral-200 cursor-pointer">
              <input
                type="checkbox"
                checked={selected.size === 0}
                onChange={clear}
                className="accent-white"
              />
              <span>All</span>
              <span className="font-mono text-neutral-500">{items.length}</span>
            </label>
            <div className="flex items-center gap-3 text-[11px]">
              {selected.size > 0 && (
                <button
                  type="button"
                  onClick={clear}
                  className="text-neutral-500 hover:text-white transition"
                >
                  Clear
                </button>
              )}
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="text-neutral-300 hover:text-white transition"
              >
                Done
              </button>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-x-3 gap-y-1">
            {tickers.map((t) => {
              const count = countsByTicker.get(t) ?? 0;
              const disabled = count === 0;
              return (
                <label
                  key={t}
                  className={`inline-flex items-center gap-1.5 text-xs ${
                    disabled
                      ? "text-neutral-600 cursor-not-allowed"
                      : "text-neutral-200 cursor-pointer"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={selected.has(t)}
                    onChange={() => toggle(t)}
                    disabled={disabled}
                    className="accent-white"
                  />
                  <span className="font-mono">{t}</span>
                  <span className="font-mono text-neutral-500">{count}</span>
                </label>
              );
            })}
          </div>
        </div>
      )}

      {!loading && filtered.length === 0 && (
        <div className="text-sm text-neutral-500">
          {selected.size === 0
            ? "No recent news available for the current holdings."
            : "No recent news for the selected stocks."}
        </div>
      )}

      <ul className="divide-y divide-white/[0.07]">
        {filtered.map((item, i) => (
          <li key={`${item.ticker}-${i}`} className="py-2 first:pt-0 last:pb-0">
            <div className="flex items-start gap-2">
              <span className="control shrink-0 mt-0.5 inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-mono uppercase tracking-wider text-neutral-300">
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
