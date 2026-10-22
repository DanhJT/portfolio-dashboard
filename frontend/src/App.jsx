import React, { useCallback, useEffect, useMemo, useState } from "react";
import TabNav from "./components/TabNav.jsx";
import AboutTab from "./components/tabs/AboutTab.jsx";
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
  { key: "about", label: "About" },
];

function PeriodSelector({ value, onChange, disabled }) {
  return (
    <div
      className="control inline-flex overflow-hidden"
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
            className={`px-2 py-1 text-[11px] font-medium transition ${
              active
                ? "bg-white text-black"
                : "bg-transparent text-neutral-300 hover:bg-white/5"
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
    <div className="hidden lg:inline-flex items-center gap-2 text-[10px] text-neutral-400 whitespace-nowrap">
      <span className="inline-flex items-center rounded-full border border-emerald-900/60 bg-emerald-950/30 px-1.5 py-px font-medium text-emerald-300">
        {label}
      </span>
      {rebalanced && (
        <span className="font-mono text-neutral-400" title={`Rebalanced ${rebalanced}`}>
          Rebal. {rebalanced}
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
      strategy: activePortfolio.strategy,
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
    <div className="min-h-screen bg-chassis text-white">
      {/* Single bar: title · tabs · controls. Kept to ~44px so the fixed-height
          Overview layout below gets the vertical space. */}
      <header className="sticky top-0 z-20 border-b rule bg-chassis/95 backdrop-blur">
        <div className="mx-auto max-w-[1600px] px-6 min-h-[2.75rem] flex flex-wrap items-stretch gap-x-4">
          <div className="flex items-center gap-4">
            <h1 className="text-sm font-semibold tracking-tight text-white whitespace-nowrap">
              Portfolio Risk<span className="hidden xl:inline"> Dashboard</span>
            </h1>
            <span className="h-4 w-px bg-white/10" aria-hidden />
          </div>
          <TabNav tabs={MAIN_TABS} active={activeTab} onChange={setActiveTab} />
          <div className="ml-auto flex items-center gap-3 py-1.5">
            <StrategyBadge portfolio={activePortfolio} />
            <PeriodSelector
              value={period}
              onChange={setPeriod}
              disabled={loading}
            />
            <button
              type="button"
              onClick={refresh}
              disabled={loading}
              className="control control-hover inline-flex h-7 w-7 items-center justify-center text-neutral-200 disabled:cursor-not-allowed disabled:opacity-60"
              aria-label="Refresh data"
              title="Refresh data"
            >
              <RefreshIcon spinning={loading} />
            </button>
            <div
              className="text-[10px] text-neutral-400 font-mono whitespace-nowrap"
              title={IS_STATIC ? "Daily snapshot · data from Yahoo Finance" : "Live data from Yahoo Finance"}
            >
              {updatedAt
                ? IS_STATIC
                  ? `As of ${updatedAt.toLocaleDateString()}`
                  : `Updated ${updatedAt.toLocaleTimeString()}`
                : "Loading…"}
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1600px] px-6 py-3 space-y-3">
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
        {activeTab === "about" && (
          <AboutTab portfolio={activePortfolio} strategyLabels={STRATEGY_LABELS} />
        )}
      </main>

      <footer className="mx-auto max-w-[1600px] px-6 py-4 text-xs text-neutral-400">
        Educational use only. Not investment advice. Market data via yfinance.
      </footer>
    </div>
  );
}
