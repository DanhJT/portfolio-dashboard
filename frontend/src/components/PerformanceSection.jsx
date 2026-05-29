import React from "react";
import PerformanceChart from "./PerformanceChart.jsx";
import RelativePerformanceChart from "./RelativePerformanceChart.jsx";

const PERIOD_LABELS = {
  "3mo": "3M",
  "6mo": "6M",
  "1y": "1Y",
  "2y": "2Y",
};

/**
 * Visual grouping for the cumulative + excess return charts. The shared
 * header with the horizon pill makes it explicit that the period selector
 * (in the page header) governs both charts at once.
 */
export default function PerformanceSection({
  series,
  benchmarkTicker = "SPY",
  period,
  compact = false,
}) {
  const periodLabel = PERIOD_LABELS[period] ?? period;
  return (
    <section className="space-y-3">
      {!compact && (
        <div className="flex items-center justify-between px-1">
          <h2 className="text-sm uppercase tracking-wider text-neutral-400">
            Performance
          </h2>
          <span
            className="inline-flex items-center rounded-full border border-neutral-700 bg-black px-2.5 py-0.5 text-xs font-mono text-neutral-200"
            aria-label={`Current horizon: ${periodLabel}`}
          >
            {periodLabel}
          </span>
        </div>
      )}
      <PerformanceChart series={series} benchmarkTicker={benchmarkTicker} chartHeight={compact ? "h-40" : "h-64"} />
      <RelativePerformanceChart
        series={series}
        benchmarkTicker={benchmarkTicker}
        chartHeight={compact ? "h-28" : "h-48"}
      />
    </section>
  );
}
