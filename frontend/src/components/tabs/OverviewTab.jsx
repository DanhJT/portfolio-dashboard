import React, { useEffect, useMemo, useState } from "react";
import { getGarch, getLiquidity, getMonteCarlo, getStressTests } from "../../api.js";
import NewsPanel from "../NewsPanel.jsx";
import PerformanceSection from "../PerformanceSection.jsx";
import RiskMetricsPanel from "../RiskMetricsPanel.jsx";

const pct = (v, d = 1) =>
  v === null || v === undefined || Number.isNaN(v)
    ? "—"
    : `${(v * 100).toFixed(d)}%`;

function ArrowIcon() {
  return (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M5 12h14M12 5l7 7-7 7" />
    </svg>
  );
}

function SnapshotHeader({ title, onNavigate, tab }) {
  return (
    <div className="flex items-center justify-between">
      <h3 className="text-[10px] uppercase tracking-wider text-neutral-400">{title}</h3>
      <button
        type="button"
        onClick={() => onNavigate(tab)}
        className="inline-flex items-center gap-1 text-[10px] text-neutral-500 hover:text-white transition"
      >
        Details <ArrowIcon />
      </button>
    </div>
  );
}

function SkeletonCard({ rows = 2 }) {
  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-950 p-3 space-y-2 animate-pulse">
      <div className="h-2.5 w-28 bg-neutral-800 rounded" />
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-4 bg-neutral-800 rounded w-full" />
      ))}
    </div>
  );
}

function RiskSnapshotCard({ onNavigate }) {
  const [mc, setMc] = useState(null);
  const [garch, setGarch] = useState(null);
  const [stress, setStress] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getMonteCarlo(), getGarch(), getStressTests()])
      .then(([m, g, s]) => {
        if (cancelled) return;
        setMc(m);
        setGarch(g);
        setStress(s.scenarios);
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  if (loading) return <SkeletonCard rows={5} />;

  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-950 p-3 space-y-2">
      <SnapshotHeader title="Risk Snapshot" onNavigate={onNavigate} tab="risk" />

      {/* VaR / CVaR / GARCH row */}
      <div className="flex gap-2">
        {[
          { label: "VaR 95%", value: pct(mc?.var_95), tone: "text-amber-300" },
          { label: "CVaR 95%", value: pct(mc?.cvar_95), tone: "text-rose-300" },
          { label: "GARCH Vol", value: pct(garch?.forecast_vol), tone: "text-amber-300" },
        ].map(({ label, value, tone }) => (
          <div key={label} className="flex-1 rounded-lg border border-neutral-800 bg-black px-2 py-1.5 min-w-0">
            <div className="text-[9px] uppercase tracking-wider text-neutral-500">{label}</div>
            <div className={`font-mono text-sm font-semibold mt-0.5 ${tone}`}>{value}</div>
          </div>
        ))}
      </div>

      {/* Stress test table — all scenarios */}
      {stress?.length > 0 && (
        <div>
          <div className="text-[9px] uppercase tracking-wider text-neutral-500 mb-1">Historical Stress Tests</div>
          <table className="w-full text-[11px] font-mono">
            <thead>
              <tr className="text-neutral-500 border-b border-neutral-800">
                <th className="font-sans font-normal text-left pb-0.5">Scenario</th>
                <th className="font-sans font-normal text-right pb-0.5">Return</th>
                <th className="font-sans font-normal text-right pb-0.5">Max DD</th>
              </tr>
            </thead>
            <tbody>
              {stress.map((s) => (
                <tr key={s.name} className="border-b border-neutral-900 last:border-b-0">
                  <td className="py-0.5 pr-2 text-neutral-300 truncate max-w-[120px]" style={{ maxWidth: "9rem" }}>
                    {s.name.replace(/_/g, " ")}
                  </td>
                  <td className={`py-0.5 text-right ${s.portfolio_return < -0.3 ? "text-rose-300" : s.portfolio_return < -0.1 ? "text-amber-300" : "text-neutral-300"}`}>
                    {pct(s.portfolio_return, 1)}
                  </td>
                  <td className="py-0.5 text-right text-rose-400">
                    {pct(s.max_drawdown, 1)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function LiquiditySnapshotCard({ onNavigate }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    getLiquidity()
      .then((d) => { if (!cancelled) setData(d); })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  if (loading) return <SkeletonCard rows={6} />;

  const positions = data?.positions ?? [];

  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-950 p-3 space-y-2">
      <SnapshotHeader title="Liquidity Snapshot" onNavigate={onNavigate} tab="liquidity" />

      {positions.length > 0 && (
        <table className="w-full text-[11px] font-mono">
          <thead>
            <tr className="text-neutral-500 border-b border-neutral-800">
              <th className="font-sans font-normal text-left pb-0.5">Ticker</th>
              <th className="font-sans font-normal text-right pb-0.5">Kelly</th>
              <th className="font-sans font-normal text-right pb-0.5">% ADV</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p) => {
              const flagged = Math.abs(p.kelly_divergence) > 0.10;
              return (
                <tr key={p.ticker} className="border-b border-neutral-900 last:border-b-0">
                  <td className={`py-0.5 pr-2 font-sans ${flagged ? "text-amber-300" : "text-neutral-200"}`}>
                    {p.ticker}
                    {flagged && <span className="ml-1 text-[9px] text-amber-500">▲</span>}
                  </td>
                  <td className="py-0.5 text-right text-sky-300">{pct(p.kelly_weight)}</td>
                  <td className={`py-0.5 text-right ${p.pct_of_adv > 0.05 ? "text-amber-300" : "text-neutral-400"}`}>
                    {pct(p.pct_of_adv, 3)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default function OverviewTab({
  metrics,
  prices,
  news,
  loading,
  portfolio,
  period,
  onNavigate,
}) {
  return (
    <div className="flex flex-col gap-3 h-[calc(100vh-9.5rem)]">
      <RiskMetricsPanel metrics={metrics} compact />

      <div className="grid grid-cols-12 gap-4 flex-1 min-h-0">
        {/* Left 60% — performance charts, no section header so top aligns with right column */}
        <div className="col-span-7 min-h-0 overflow-hidden">
          <PerformanceSection
            series={prices?.series}
            benchmarkTicker={prices?.benchmark_ticker}
            period={period}
            compact
          />
        </div>

        {/* Right 40% — snapshot cards + news */}
        <div className="col-span-5 flex flex-col gap-3 min-h-0">
          <RiskSnapshotCard onNavigate={onNavigate} />
          <LiquiditySnapshotCard onNavigate={onNavigate} />
          <div className="flex-1 min-h-0 overflow-y-auto rounded-xl border border-neutral-800 bg-neutral-950 p-3">
            <div className="text-[10px] uppercase tracking-wider text-neutral-400 mb-2">News</div>
            <NewsPanel
              news={news}
              loading={loading && !news}
              tickers={portfolio?.tickers ?? []}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
