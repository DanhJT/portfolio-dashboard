import React from "react";
import { AXIS, GRID, SERIES, TICK } from "../chartTheme.js";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const pct = (v) => `${(v * 100).toFixed(1)}%`;

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const v = payload[0].value;
  const color = v >= 0 ? SERIES.positive : SERIES.negative;
  return (
    <div className="control px-3 py-2 text-xs shadow-xl shadow-black/60">
      <div className="text-neutral-400 mb-1">{label}</div>
      <div className="flex items-center gap-2 font-mono">
        <span
          className="inline-block h-2 w-2 rounded-full"
          style={{ background: color }}
        />
        <span className="text-neutral-300">excess</span>
        <span className="ml-auto" style={{ color }}>
          {v >= 0 ? "+" : ""}
          {pct(v)}
        </span>
      </div>
    </div>
  );
}

export default function RelativePerformanceChart({
  series,
  benchmarkTicker = "SPY",
  chartHeight = "h-48",
}) {
  if (!series?.length) {
    return (
      <div className={`panel p-5 ${chartHeight} flex items-center justify-center text-neutral-500 text-sm`}>
        Loading relative performance…
      </div>
    );
  }

  const data = series.map((p) => ({
    date: p.date,
    excess: (p.portfolio ?? 0) - (p.benchmark ?? 0),
  }));

  const last = data[data.length - 1]?.excess ?? 0;
  const lastColor = last >= 0 ? "text-emerald-400" : "text-rose-400";

  return (
    <div className="panel p-5">
      <div className="flex items-baseline justify-between mb-3">
        <div>
          <h2 className="text-sm uppercase tracking-wider text-neutral-400">
            Excess Return vs {benchmarkTicker}
          </h2>
          <p className="text-xs text-neutral-500 mt-0.5">
            Portfolio minus benchmark · above 0 = outperforming
          </p>
        </div>
        <div className={`font-mono text-lg ${lastColor}`}>
          {last >= 0 ? "+" : ""}
          {pct(last)}
        </div>
      </div>
      <div className={chartHeight}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={data}
            margin={{ top: 8, right: 12, left: 0, bottom: 0 }}
          >
            <defs>
              <linearGradient id="excess-pos" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={SERIES.positive} stopOpacity={0.45} />
                <stop offset="100%" stopColor={SERIES.positive} stopOpacity={0} />
              </linearGradient>
              <linearGradient id="excess-neg" x1="0" y1="1" x2="0" y2="0">
                <stop offset="0%" stopColor={SERIES.negative} stopOpacity={0.45} />
                <stop offset="100%" stopColor={SERIES.negative} stopOpacity={0} />
              </linearGradient>
            </defs>
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
            <ReferenceLine y={0} stroke={SERIES.zero} strokeDasharray="2 2" />
            <Area
              type="monotone"
              dataKey="excess"
              stroke={SERIES.benchmark}
              strokeWidth={0}
              fill="url(#excess-pos)"
              isAnimationActive={false}
              baseValue={0}
            />
            <Area
              type="monotone"
              dataKey={(d) => Math.min(d.excess, 0)}
              stroke="transparent"
              fill="url(#excess-neg)"
              isAnimationActive={false}
              baseValue={0}
              activeDot={false}
            />
            <Area
              type="monotone"
              dataKey="excess"
              stroke={SERIES.neutral}
              strokeWidth={1.5}
              fill="transparent"
              isAnimationActive={false}
              activeDot={{ r: 3, fill: SERIES.neutral }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
