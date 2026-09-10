import React from "react";
import { AXIS, GRID, LEGEND, SERIES, TICK } from "../chartTheme.js";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const pct = (v) => `${(v * 100).toFixed(1)}%`;

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="control px-3 py-2 text-xs shadow-xl shadow-black/60">
      <div className="text-neutral-400 mb-1">{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="flex items-center gap-2 font-mono">
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ background: p.color }}
          />
          <span className="text-neutral-300 capitalize">{p.dataKey}</span>
          <span className="ml-auto text-white">{pct(p.value)}</span>
        </div>
      ))}
    </div>
  );
}

export default function PerformanceChart({ series, benchmarkTicker = "SPY", chartHeight = "h-64" }) {
  if (!series?.length) {
    return (
      <div className={`panel p-5 ${chartHeight} flex items-center justify-center text-neutral-500 text-sm`}>
        Loading performance series…
      </div>
    );
  }

  const data = series.map((p) => ({
    date: p.date,
    portfolio: p.portfolio,
    benchmark: p.benchmark,
  }));

  return (
    <div className="panel p-5">
      <div className="flex items-baseline justify-between mb-3">
        <h2 className="text-sm uppercase tracking-wider text-neutral-400">
          Cumulative Return
        </h2>
        <span className="text-xs text-neutral-500">
          vs {benchmarkTicker}
        </span>
      </div>
      <div className={chartHeight}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={data}
            margin={{ top: 8, right: 12, left: 0, bottom: 0 }}
          >
            <CartesianGrid stroke={GRID} strokeDasharray="3 3" />
            <XAxis
              dataKey="date"
              tick={{ fill: TICK, fontSize: 11 }}
              stroke={AXIS}
              minTickGap={32}
            />
            <YAxis
              tick={{ fill: TICK, fontSize: 11 }}
              stroke={AXIS}
              tickFormatter={pct}
              width={56}
            />
            <Tooltip content={<ChartTooltip />} />
            <Legend
              wrapperStyle={{ fontSize: 12, color: LEGEND }}
              iconType="circle"
            />
            <Line
              type="monotone"
              dataKey="portfolio"
              stroke={SERIES.portfolio}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="benchmark"
              stroke={SERIES.benchmark}
              strokeWidth={1.5}
              strokeDasharray="4 3"
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
