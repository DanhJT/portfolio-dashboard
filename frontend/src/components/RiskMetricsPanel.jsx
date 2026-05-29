import React from "react";

const pct = (v, digits = 2) =>
  v === null || v === undefined || Number.isNaN(v)
    ? "—"
    : `${(v * 100).toFixed(digits)}%`;

const num = (v, digits = 2) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : v.toFixed(digits);

function MetricCard({ label, value, tone = "neutral", tooltip, compact = false }) {
  const toneClass =
    tone === "good"
      ? "text-emerald-400"
      : tone === "bad"
        ? "text-rose-400"
        : tone === "warn"
          ? "text-amber-400"
          : "text-white";
  return (
    <div className={`group relative rounded-lg border border-neutral-800 bg-neutral-950 ${compact ? "px-2.5 py-1.5" : "px-3 py-2.5"}`}>
      <div className={`${compact ? "text-[9px]" : "text-[10px]"} uppercase tracking-wider text-neutral-400`}>
        {label}
      </div>
      <div className={`font-mono font-semibold tracking-tight mt-0.5 ${compact ? "text-sm" : "text-lg"} ${toneClass}`}>
        {value}
      </div>
      {!compact && tooltip && (
        <div className="pointer-events-none absolute left-0 top-full mt-2 w-64 rounded-md border border-neutral-800 bg-neutral-950 p-3 text-xs text-neutral-300 opacity-0 shadow-lg transition group-hover:opacity-100 z-10">
          {tooltip}
        </div>
      )}
    </div>
  );
}

export default function RiskMetricsPanel({ metrics, compact = false }) {
  if (!metrics) {
    return (
      <div className="grid grid-cols-4 md:grid-cols-8 gap-2">
        {Array.from({ length: 8 }).map((_, i) => (
          <div
            key={i}
            className={`rounded-lg border border-neutral-800 bg-neutral-950 ${compact ? "h-9" : "h-14"} animate-pulse`}
            aria-hidden
          />
        ))}
      </div>
    );
  }

  const sharpeTone =
    metrics.sharpe_ratio >= 1
      ? "good"
      : metrics.sharpe_ratio >= 0
        ? "warn"
        : "bad";
  const retTone = metrics.annualised_return >= 0 ? "good" : "bad";
  const volTone =
    metrics.annualised_volatility < 0.2
      ? "good"
      : metrics.annualised_volatility < 0.35
        ? "warn"
        : "bad";

  const alphaTone = metrics.alpha > 0.02 ? "good" : metrics.alpha > 0 ? "warn" : "bad";
  const betaTone = metrics.beta < 0.8 ? "good" : metrics.beta < 1.2 ? "neutral" : "warn";

  return (
    <div className="grid grid-cols-4 md:grid-cols-8 gap-2">
      <MetricCard compact={compact} label="Ann. Return" value={pct(metrics.annualised_return)} tone={retTone} tooltip="Compound annual growth rate of the portfolio over the selected period." />
      <MetricCard compact={compact} label="Ann. Volatility" value={pct(metrics.annualised_volatility)} tone={volTone} tooltip="Standard deviation of daily returns × √252. A measure of total risk." />
      <MetricCard compact={compact} label="Sharpe" value={num(metrics.sharpe_ratio)} tone={sharpeTone} tooltip="Excess return over the 4.5% risk-free rate per unit of volatility. >1 is generally considered good." />
      <MetricCard compact={compact} label="Alpha (ann.)" value={pct(metrics.alpha)} tone={alphaTone} tooltip="Jensen's alpha vs SPY: annualised excess return above what CAPM predicts given the portfolio's beta." />
      <MetricCard compact={compact} label="Beta" value={num(metrics.beta, 2)} tone={betaTone} tooltip="Sensitivity to SPY movements. β < 1 = less volatile than market, β > 1 = more volatile." />
      <MetricCard compact={compact} label="Max Drawdown" value={pct(metrics.max_drawdown)} tone="bad" tooltip="Largest peak-to-trough decline in the cumulative return curve over the period." />
      <MetricCard compact={compact} label="VaR 95%" value={pct(metrics.var_95)} tone="warn" tooltip="Historical Value-at-Risk: with 95% confidence, daily losses should not exceed this figure." />
      <MetricCard compact={compact} label="CVaR 95%" value={pct(metrics.cvar_95)} tone="bad" tooltip="Expected Shortfall: average loss on days when the VaR threshold is breached." />
    </div>
  );
}
