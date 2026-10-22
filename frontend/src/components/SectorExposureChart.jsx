import React, { useId } from "react";
import { CATEGORICAL_DEEP, SERIES, TICK } from "../chartTheme.js";
import { SECTOR_BY_TICKER, SP500_SECTOR_WEIGHTS, SP500_WEIGHTS_AS_OF } from "../sectors.js";
import { Bar, BarChart, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const pct = (v) => `${(v * 100).toFixed(1)}%`;
const pct0 = (v) => `${Math.round(v * 100)}%`;
const MAX_SECTOR_ROWS = 5;

function ChartTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const { sector, portfolio, sp500, holdings } = payload[0].payload;
  const diff = (portfolio - sp500) * 100;
  return (
    <div className="control px-3 py-2 text-[10px] shadow-xl shadow-black/60 space-y-1">
      <div className="text-neutral-300">{sector}</div>
      <div className="flex items-center gap-2 font-mono">
        <span className="inline-block h-2 w-2 rounded-full" style={{ background: SERIES.portfolio }} />
        <span className="text-neutral-400">Portfolio</span>
        <span className="ml-auto pl-3 text-neutral-100">{pct(portfolio)}</span>
      </div>
      <div className="flex items-center gap-2 font-mono">
        <span className="inline-block h-2 w-2 rounded-full" style={{ background: SERIES.benchmark }} />
        <span className="text-neutral-400">S&amp;P 500</span>
        <span className="ml-auto pl-3 text-neutral-100">{pct(sp500)}</span>
      </div>
      <div className="font-mono text-neutral-300 border-t rule pt-1">
        {diff >= 0 ? "+" : ""}
        {diff.toFixed(1)} pp
      </div>
      {holdings.length > 0 && (
        <div className="font-mono text-neutral-500">
          {holdings.map((h) => `${h.ticker} ${(h.weight * 100).toFixed(1)}`).join(" · ")}
        </div>
      )}
    </div>
  );
}

function buildRows(portfolio) {
  const bySector = new Map();
  portfolio.tickers.forEach((ticker, i) => {
    const sector = SECTOR_BY_TICKER[ticker] ?? "Other";
    const row = bySector.get(sector) ?? { sector, portfolio: 0, holdings: [] };
    row.portfolio += portfolio.weights[i] ?? 0;
    row.holdings.push({ ticker, weight: portfolio.weights[i] ?? 0 });
    bySector.set(sector, row);
  });

  const unmapped = bySector.get("Other");
  bySector.delete("Other");

  const held = [...bySector.values()]
    .map((r) => ({
      ...r,
      sp500: SP500_SECTOR_WEIGHTS[r.sector] ?? 0,
      holdings: r.holdings.sort((a, b) => b.weight - a.weight),
    }))
    .sort((a, b) => b.portfolio - a.portfolio);

  // Keep the panel readable: largest held sectors, then everything else
  // (smaller held sectors + unmapped tickers + unheld S&P weight) in "Other".
  const shown = held.slice(0, MAX_SECTOR_ROWS);
  const rest = held.slice(MAX_SECTOR_ROWS);
  const shownSp = shown.reduce((s, r) => s + r.sp500, 0);
  const otherHoldings = [...rest.flatMap((r) => r.holdings), ...(unmapped?.holdings ?? [])]
    .sort((a, b) => b.weight - a.weight);
  shown.push({
    sector: "Other",
    portfolio: otherHoldings.reduce((s, h) => s + h.weight, 0),
    sp500: Math.max(0, 1 - shownSp),
    holdings: otherHoldings,
  });
  return shown;
}

export default function SectorExposureChart({ portfolio, chartHeight = "h-36" }) {
  const gradientId = `se-${useId().replace(/:/g, "")}`;

  if (!portfolio?.tickers?.length) {
    return (
      <div className={`panel p-5 ${chartHeight} flex items-center justify-center text-neutral-500 text-sm`}>
        Loading sectors…
      </div>
    );
  }

  const data = buildRows(portfolio);
  const max = Math.max(...data.flatMap((r) => [r.portfolio, r.sp500]));

  return (
    <div className="panel p-4">
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-xs uppercase tracking-wider text-neutral-400">Sector Exposure</h2>
          <p className="text-[10px] text-neutral-500 mt-0.5 truncate">
            vs S&amp;P 500 · {SP500_WEIGHTS_AS_OF}
          </p>
        </div>
        <div className="flex items-center gap-2 text-[9px] text-neutral-400 shrink-0 mt-0.5">
          <span className="flex items-center gap-1">
            <span
              className="inline-block h-2 w-2 rounded-sm"
              style={{ background: `linear-gradient(135deg, ${SERIES.portfolio}, ${CATEGORICAL_DEEP[0]})` }}
            />
            Portfolio
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-sm" style={{ background: SERIES.benchmark }} />
            S&amp;P
          </span>
        </div>
      </div>
      <div className={chartHeight}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            layout="vertical"
            margin={{ top: 0, right: 28, left: 0, bottom: 0 }}
            barGap={2}
            barCategoryGap="22%"
          >
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stopColor={CATEGORICAL_DEEP[0]} />
                <stop offset="100%" stopColor={SERIES.portfolio} />
              </linearGradient>
            </defs>
            <XAxis type="number" hide domain={[0, max]} />
            <YAxis
              type="category"
              dataKey="sector"
              width={72}
              tick={{ fill: TICK, fontSize: 9 }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
            <Bar
              dataKey="portfolio"
              fill={`url(#${gradientId})`}
              radius={[0, 4, 4, 0]}
              isAnimationActive={false}
              style={{ filter: `drop-shadow(0 0 3px ${SERIES.portfolio}55)` }}
            >
              <LabelList dataKey="portfolio" position="right" formatter={pct0} fill={TICK} fontSize={9} />
            </Bar>
            <Bar dataKey="sp500" fill={SERIES.benchmark} fillOpacity={0.55} radius={[0, 4, 4, 0]} isAnimationActive={false}>
              <LabelList dataKey="sp500" position="right" formatter={pct0} fill={TICK} fontSize={9} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
