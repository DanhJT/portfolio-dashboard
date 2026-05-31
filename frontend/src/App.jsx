import React, { useCallback, useEffect, useMemo, useState } from "react";
import TabNav from "./components/TabNav.jsx";
import LiquidityTab from "./components/tabs/LiquidityTab.jsx";
import OverviewTab from "./components/tabs/OverviewTab.jsx";
import RiskTab from "./components/tabs/RiskTab.jsx";
import {
  getCurrentPortfolio,
  getMetrics,
  getNews,
  getPrices,
  getSnapshotMeta,
  IS_STATIC,
} from "./api.js";

const PERIODS = [
  { value: "3mo", label: "3M" },
  { value: "6mo", label: "6M" },
  { value: "1y", label: "1Y" },
  { value: "2y", label: "2Y" },
];

const STRATEGY_LABELS = {
  "value-momentum": "Value-Momentum",
};

const MAIN_TABS = [
  { key: "overview", label: "Overview" },
  { key: "risk", label: "Risk Models" },
  { key: "liquidity", label: "Liquidity" },
];

function PeriodSelector({ value, onChange, disabled }) {
  return (
    <div
      className="inline-flex rounded-md border border-neutral-800 overflow-hidden"
      title="Horizon — applies to metrics & charts"
    >
      {PERIODS.map((p) => {
        const active = value === p.value;
        return (
          <button
            key={p.value}
            type="button"
            onClick={() => onChange(p.value)}
            disabled={disabled}
            className={`px-3 py-1.5 text-xs font-medium transition ${
              active
                ? "bg-white text-black"
                : "bg-black text-neutral-300 hover:bg-neutral-900"
            }`}
          >
            {p.label}
          </button>
        );
      })}
    </div>
  );
}

function RefreshIcon({ spinning }) {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={spinning ? "animate-spin" : ""}
      aria-hidden
    >
      <path d="M21 12a9 9 0 1 1-3.2-6.9" />
      <polyline points="21 4 21 10 15 10" />
    </svg>
  );
}

function StrategyBadge({ portfolio }) {
  if (!portfolio) return null;
  const label = STRATEGY_LABELS[portfolio.strategy] ?? portfolio.strategy;
  const rebalanced = portfolio.rebalanced_at
    ? new Date(portfolio.rebalanced_at).toLocaleDateString()
    : null;
  return (
    <div className="inline-flex items-center gap-2 text-xs text-neutral-400">
      <span className="inline-flex items-center rounded-full border border-emerald-900/60 bg-emerald-950/30 px-2 py-0.5 text-[11px] font-medium text-emerald-300">
        {label}
      </span>
      {rebalanced && (
        <span className="font-mono text-neutral-500">
          Rebalanced {rebalanced}
        </span>
      )}
    </div>
  );
}

export default function App() {
  const [activeTab, setActiveTab] = useState("overview");
  const [period, setPeriod] = useState("1y");
  const [activePortfolio, setActivePortfolio] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [prices, setPrices] = useState(null);
  const [news, setNews] = useState(null);
  const [updatedAt, setUpdatedAt] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const portfolio = useMemo(() => {
    if (!activePortfolio) return null;
    return {
      tickers: activePortfolio.tickers,
      weights: activePortfolio.weights,
      period,
    };
  }, [activePortfolio, period]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const current = await getCurrentPortfolio();
      setActivePortfolio(current);
      const fetchPortfolio = {
        tickers: current.tickers,
        weights: current.weights,
        period,
      };
      const [m, p, n, meta] = await Promise.all([
        getMetrics(fetchPortfolio),
        getPrices(fetchPortfolio),
        getNews(fetchPortfolio),
        getSnapshotMeta(),
      ]);
      setMetrics(m);
      setPrices(p);
      setNews(n);
      setUpdatedAt(meta?.generated_at ? new Date(meta.generated_at) : new Date());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [period]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <div className="min-h-screen bg-black text-white">
      <header className="sticky top-0 z-20 border-b border-neutral-900 bg-black/95 backdrop-blur">
        <div className="mx-auto max-w-[1600px] px-6 py-4 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-white">
              Portfolio Risk Dashboard
            </h1>
            <div className="mt-1 flex items-center gap-3">
              <p className="text-xs text-neutral-400">
                {IS_STATIC ? "Daily snapshot · data from Yahoo Finance" : "Live data from Yahoo Finance"}
              </p>
              <StrategyBadge portfolio={activePortfolio} />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <PeriodSelector
              value={period}
              onChange={setPeriod}
              disabled={loading}
            />
            <button
              type="button"
              onClick={refresh}
              disabled={loading}
              className="inline-flex items-center gap-1.5 rounded-md border border-neutral-800 bg-black px-3 py-1.5 text-xs font-medium text-neutral-200 hover:bg-neutral-900 disabled:cursor-not-allowed disabled:opacity-60"
              aria-label="Refresh data"
              title="Refresh data"
            >
              <RefreshIcon spinning={loading} />
              Refresh
            </button>
            <div className="text-xs text-neutral-400 font-mono">
              {updatedAt
                ? IS_STATIC
                  ? `Data as of ${updatedAt.toLocaleDateString()}`
                  : `Updated ${updatedAt.toLocaleTimeString()}`
                : "Loading…"}
            </div>
          </div>
        </div>
        <TabNav tabs={MAIN_TABS} active={activeTab} onChange={setActiveTab} />
      </header>

      <main className="mx-auto max-w-[1600px] px-6 py-5 space-y-4">
        {error && (
          <div className="rounded-md border border-rose-900 bg-rose-950/50 p-3 text-sm text-rose-300">
            {error}
          </div>
        )}

        {activeTab === "overview" && (
          <OverviewTab
            metrics={metrics}
            prices={prices}
            news={news}
            loading={loading}
            portfolio={portfolio}
            period={period}
            onNavigate={setActiveTab}
          />
        )}
        {activeTab === "risk" && <RiskTab />}
        {activeTab === "liquidity" && <LiquidityTab />}
      </main>

      <footer className="mx-auto max-w-[1600px] px-6 py-4 text-xs text-neutral-500">
        Educational use only. Not investment advice. Market data via yfinance.
      </footer>
    </div>
  );
}
