import React from "react";

const pct = (v, digits = 2) =>
  v === null || v === undefined || Number.isNaN(v)
    ? "—"
    : `${(v * 100).toFixed(digits)}%`;

function volColor(vol) {
  if (vol < 0.2) return "text-emerald-400";
  if (vol < 0.35) return "text-amber-400";
  return "text-rose-400";
}

export default function PortfolioTable({ metrics }) {
  if (!metrics) return null;
  const rows = metrics.holdings ?? [];
  return (
    <div>
      <div className="flex items-baseline justify-between mb-3">
        <span className="text-xs text-neutral-500">
          {rows.length} positions
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-neutral-400 border-b border-neutral-800">
              <th className="py-2 pr-4 font-medium">Ticker</th>
              <th className="py-2 pr-4 font-medium text-right">Weight</th>
              <th className="py-2 pr-4 font-medium text-right">Ann. Return</th>
              <th className="py-2 pr-4 font-medium text-right">Ann. Vol</th>
              <th className="py-2 pr-0 font-medium text-right">Vol Contrib</th>
            </tr>
          </thead>
          <tbody className="font-mono">
            {rows.map((h) => (
              <tr
                key={h.ticker}
                className="border-b border-neutral-900 last:border-b-0 hover:bg-neutral-900/60"
              >
                <td className="py-2.5 pr-4 font-sans font-medium text-white">
                  {h.ticker}
                </td>
                <td className="py-2.5 pr-4 text-right text-white">
                  {pct(h.weight, 1)}
                </td>
                <td
                  className={`py-2.5 pr-4 text-right ${
                    h.annualised_return >= 0
                      ? "text-emerald-400"
                      : "text-rose-400"
                  }`}
                >
                  {pct(h.annualised_return)}
                </td>
                <td
                  className={`py-2.5 pr-4 text-right ${volColor(
                    h.annualised_volatility,
                  )}`}
                >
                  {pct(h.annualised_volatility)}
                </td>
                <td className="py-2.5 pr-0 text-right text-neutral-300">
                  {pct(h.volatility_contribution, 1)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
