import React, { useId, useState } from "react";
import { CATEGORICAL, CATEGORICAL_DEEP, SERIES } from "../chartTheme.js";
import { Cell, Pie, PieChart, ResponsiveContainer, Sector, Tooltip } from "recharts";

const pct = (v) => `${(v * 100).toFixed(1)}%`;
const RADIAN = Math.PI / 180;
// Slices thinner than this don't get an on-ring label; the legend covers them.
const LABEL_MIN_WEIGHT = 0.06;

function ChartTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const { ticker, weight, color, members } = payload[0].payload;
  return (
    <div className="control px-3 py-2 text-xs shadow-xl shadow-black/60">
      <div className="flex items-center gap-2 font-mono text-[10px]">
        <span className="inline-block h-2 w-2 rounded-full" style={{ background: color }} />
        <span className="text-neutral-300">{ticker}</span>
        <span className="ml-3 text-neutral-100">{pct(weight)}</span>
      </div>
      {members && (
        <div className="mt-1 max-w-[14rem] font-mono text-[10px] leading-snug text-neutral-500">
          {members.map((m) => `${m.ticker} ${(m.weight * 100).toFixed(1)}`).join(" · ")}
        </div>
      )}
    </div>
  );
}

function ActiveSlice(props) {
  return <Sector {...props} outerRadius={props.outerRadius + 3} />;
}

function SliceLabel({ cx, cy, midAngle, innerRadius, outerRadius, payload }) {
  if (payload.weight < LABEL_MIN_WEIGHT) return null;
  const r = innerRadius + (outerRadius - innerRadius) / 2;
  return (
    <text
      x={cx + r * Math.cos(-midAngle * RADIAN)}
      y={cy + r * Math.sin(-midAngle * RADIAN)}
      textAnchor="middle"
      dominantBaseline="central"
      className="font-mono pointer-events-none"
      fontSize={9}
      fontWeight={600}
      fill="#fff"
      stroke="rgba(0,0,0,0.45)"
      strokeWidth={2}
      paintOrder="stroke"
    >
      {Math.round(payload.weight * 100)}%
    </text>
  );
}

export default function WeightsDonutChart({ portfolio, strategy, chartHeight = "h-36" }) {
  const [activeIndex, setActiveIndex] = useState(-1);
  // useId yields ":r0:"-style ids, which break inside url(#…) references.
  const gradientPrefix = `wd-${useId().replace(/:/g, "")}`;

  if (!portfolio?.tickers?.length) {
    return (
      <div className={`panel p-5 ${chartHeight} flex items-center justify-center text-neutral-500 text-sm`}>
        Loading weights…
      </div>
    );
  }

  // Up to CATEGORICAL.length named slices, largest first; the rest fold into a
  // grey "Other" slice so hues are never cycled and the legend fits.
  const sorted = portfolio.tickers
    .map((ticker, i) => ({ ticker, weight: portfolio.weights[i] ?? 0 }))
    .sort((a, b) => b.weight - a.weight);
  const overflow = sorted.length > CATEGORICAL.length;
  const namedCount = overflow ? CATEGORICAL.length : sorted.length;
  const data = sorted.slice(0, namedCount).map((d, i) => ({
    ...d,
    color: CATEGORICAL[i],
    deep: CATEGORICAL_DEEP[i],
    gradientId: `${gradientPrefix}-${i}`,
  }));
  if (overflow) {
    const rest = sorted.slice(namedCount);
    data.push({
      ticker: `Other (${rest.length})`,
      weight: rest.reduce((s, d) => s + d.weight, 0),
      members: rest,
      color: SERIES.benchmark,
      deep: SERIES.zero,
      gradientId: `${gradientPrefix}-other`,
    });
  }

  const active = data[activeIndex];
  const assetCount = sorted.length;

  return (
    <div className="panel p-4">
      <div className="mb-2">
        <h2 className="text-xs uppercase tracking-wider text-neutral-400">Portfolio Weights</h2>
        <p className="text-[10px] text-neutral-500 mt-0.5">
          {strategy ? `${strategy} · ` : ""}
          {assetCount} holdings
        </p>
      </div>
      <div className={`${chartHeight} flex items-center gap-3`}>
        <div className="relative h-full aspect-square">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <defs>
                {data.map((d) => (
                  <linearGradient key={d.gradientId} id={d.gradientId} x1="0" y1="0" x2="1" y2="1">
                    <stop offset="0%" stopColor={d.color} />
                    <stop offset="100%" stopColor={d.deep} />
                  </linearGradient>
                ))}
              </defs>
              <Tooltip content={<ChartTooltip />} />
              <Pie
                data={data}
                dataKey="weight"
                nameKey="ticker"
                innerRadius="56%"
                outerRadius="94%"
                paddingAngle={2}
                stroke="none"
                isAnimationActive={false}
                label={SliceLabel}
                labelLine={false}
                activeIndex={activeIndex}
                activeShape={ActiveSlice}
                onMouseEnter={(_, i) => setActiveIndex(i)}
                onMouseLeave={() => setActiveIndex(-1)}
              >
                {data.map((d) => (
                  <Cell
                    key={d.ticker}
                    fill={`url(#${d.gradientId})`}
                    style={{ filter: `drop-shadow(0 0 4px ${d.color}66)` }}
                  />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
          {/* Center readout: the hovered holding, otherwise the asset count */}
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
            <span className="font-mono text-sm" style={{ color: active ? active.color : SERIES.neutral }}>
              {active ? pct(active.weight) : assetCount}
            </span>
            <span className="text-[8px] uppercase tracking-wider text-neutral-500">
              {active ? active.ticker : "assets"}
            </span>
          </div>
        </div>
        <ul className="flex-1 min-w-0 space-y-0.5 text-[10px]">
          {data.map((d, i) => (
            <li
              key={d.ticker}
              className={`flex items-center gap-2 transition-opacity ${activeIndex >= 0 && activeIndex !== i ? "opacity-40" : ""}`}
              onMouseEnter={() => setActiveIndex(i)}
              onMouseLeave={() => setActiveIndex(-1)}
            >
              <span
                className="inline-block h-2 w-2 rounded-sm shrink-0"
                style={{ background: `linear-gradient(135deg, ${d.color}, ${d.deep})` }}
              />
              <span className="text-neutral-300 truncate">{d.ticker}</span>
              <span className="ml-auto font-mono text-neutral-400">{pct(d.weight)}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
