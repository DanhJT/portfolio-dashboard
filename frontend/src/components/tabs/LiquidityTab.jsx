import React, { useCallback, useEffect, useMemo, useState } from "react";
import { getLiquidity } from "../../api.js";
import CommentaryButton from "../CommentaryButton.jsx";

const fmt$ = (v) =>
  v === null || v === undefined ? "—" : `$${(v / 1_000_000).toFixed(2)}M`;

const fmtPct = (v, d = 1) =>
  v === null || v === undefined || Number.isNaN(v)
    ? "—"
    : `${(v * 100).toFixed(d)}%`;

const SCORE_STYLE = {
  5: "text-emerald-300 font-semibold",
  4: "text-emerald-400",
  3: "text-amber-300",
  2: "text-orange-400",
  1: "text-rose-300 font-semibold",
};

const SCORE_LABEL = {
  5: "Excellent",
  4: "Good",
  3: "Fair",
  2: "Low",
  1: "Illiquid",
};

function ScoreBadge({ score }) {
  const style = SCORE_STYLE[score] ?? "text-neutral-400";
  const label = SCORE_LABEL[score] ?? String(score);
  return (
    <span className={style}>
      {score} — {label}
    </span>
  );
}

function AumInput({ value, onCommit }) {
  const [draft, setDraft] = useState(String(value));

  function handleKey(e) {
    if (e.key === "Enter") commit();
  }

  function commit() {
    const n = parseFloat(draft.replace(/[^0-9.]/g, ""));
    if (n > 0) onCommit(n);
    else setDraft(String(value));
  }

  return (
    <div className="flex items-center gap-2">
      <label className="text-xs text-neutral-400 whitespace-nowrap">AUM ($)</label>
      <input
        type="text"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={handleKey}
        className="w-36 rounded border border-neutral-800 bg-black px-2 py-1 text-sm text-neutral-200 font-mono focus:outline-none focus:border-neutral-600"
      />
      <button
        type="button"
        onClick={commit}
        className="rounded border border-neutral-800 px-2 py-1 text-xs text-neutral-400 hover:bg-neutral-900 hover:text-white"
      >
        Apply
      </button>
    </div>
  );
}

export default function LiquidityTab() {
  const [aum, setAum] = useState(1_000_000);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetch = useCallback((aumValue) => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getLiquidity(aumValue)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => fetch(aum), [aum, fetch]);

  function handleAumCommit(val) {
    setAum(val);
  }

  const commentaryMetrics = useMemo(() => {
    if (!data) return null;
    return { aum: data.aum, positions: data.positions };
  }, [data]);

  if (loading) {
    return (
      <div className="text-sm text-neutral-500 p-6">
        Fetching ADV data and computing Kelly sizes…
      </div>
    );
  }
  if (error) {
    return (
      <div className="rounded-md border border-rose-900 bg-rose-950/50 p-3 text-sm text-rose-300">
        {error}
      </div>
    );
  }
  if (!data) return null;

  const { positions } = data;

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-neutral-800 bg-neutral-950 p-4 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm uppercase tracking-wider text-neutral-400">
              Liquidity &amp; Kelly Sizing
            </h2>
            <p className="text-xs text-neutral-500 mt-0.5">
              30-day ADV · Kelly f* = (μ−rf) / σ² normalised to unit leverage
            </p>
          </div>
          <AumInput value={aum} onCommit={handleAumCommit} />
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm font-mono">
            <thead>
              <tr className="text-left text-neutral-400 border-b border-neutral-800">
                <th className="py-2 pr-4 font-sans font-medium">Ticker</th>
                <th className="py-2 pr-4 font-sans font-medium text-right">ADV</th>
                <th className="py-2 pr-4 font-sans font-medium text-right">Position</th>
                <th className="py-2 pr-4 font-sans font-medium text-right">% of ADV</th>
                <th className="py-2 pr-4 font-sans font-medium text-right">Days to Liq. (10%)</th>
                <th className="py-2 pr-4 font-sans font-medium text-right">Liq. Score</th>
                <th className="py-2 pr-4 font-sans font-medium text-right">Kelly Size</th>
                <th className="py-2 pr-0 font-sans font-medium text-right">Current Wt</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p) => {
                const kellyDivergent = Math.abs(p.kelly_divergence) > 0.10;
                return (
                  <tr
                    key={p.ticker}
                    className={`border-b border-neutral-900 last:border-b-0 ${
                      kellyDivergent ? "bg-amber-950/20" : ""
                    }`}
                  >
                    <td className="py-2 pr-4 font-sans text-white">
                      {p.ticker}
                      {kellyDivergent && (
                        <span
                          className="ml-1.5 inline-flex items-center rounded-full border border-amber-900/60 bg-amber-950/50 px-1.5 py-0 text-[10px] text-amber-300"
                          title={`Kelly divergence: ${fmtPct(p.kelly_divergence)}`}
                        >
                          Δ&gt;10pp
                        </span>
                      )}
                    </td>
                    <td className="py-2 pr-4 text-right text-neutral-300">
                      {fmt$(p.adv_usd)}
                    </td>
                    <td className="py-2 pr-4 text-right text-neutral-300">
                      {fmt$(p.position_usd)}
                    </td>
                    <td className={`py-2 pr-4 text-right ${p.pct_of_adv > 0.05 ? "text-amber-300" : "text-neutral-300"}`}>
                      {fmtPct(p.pct_of_adv, 2)}
                    </td>
                    <td className={`py-2 pr-4 text-right ${p.days_to_liquidate_10 > 5 ? "text-rose-300" : p.days_to_liquidate_10 > 2 ? "text-amber-300" : "text-neutral-300"}`}>
                      {p.days_to_liquidate_10.toFixed(1)}
                    </td>
                    <td className="py-2 pr-4 text-right">
                      <ScoreBadge score={p.liquidity_score} />
                    </td>
                    <td className="py-2 pr-4 text-right text-sky-300">
                      {fmtPct(p.kelly_weight)}
                    </td>
                    <td className="py-2 pr-0 text-right text-neutral-200">
                      {fmtPct(p.current_weight)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div className="rounded-md border border-neutral-800 bg-black px-3 py-2 text-xs text-neutral-500 space-y-0.5">
          <p>
            <span className="text-amber-300">Δ&gt;10pp</span> — Kelly weight diverges &gt;10 percentage points from current weight.
          </p>
          <p>
            <span className="text-neutral-400">Days to Liq.</span> assumes liquidating at most 10% of ADV per day to limit market impact.
          </p>
        </div>
      </div>

      <CommentaryButton
        module="liquidity"
        metrics={commentaryMetrics}
        label="Generate AI Commentary"
      />
    </div>
  );
}
