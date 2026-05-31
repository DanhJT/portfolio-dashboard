import React, { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  getGarch,
  getMonteCarlo,
  getStressTests,
  postCustomStress,
  IS_STATIC,
} from "../../api.js";
import CommentaryButton from "../CommentaryButton.jsx";

const pct = (v, d = 1) =>
  v === null || v === undefined || Number.isNaN(v)
    ? "—"
    : `${(v * 100).toFixed(d)}%`;

// ---------- Monte Carlo ----------

function MonteCarloSection({ data }) {
  if (!data) return null;
  const horizon = data.horizon_days;
  const days = Array.from({ length: horizon + 1 }, (_, i) => i);
  const chartData = days.map((d) => ({
    day: d,
    p05: data.percentile_paths.p05[d],
    p25: data.percentile_paths.p25[d],
    p50: data.percentile_paths.p50[d],
    p75: data.percentile_paths.p75[d],
    p95: data.percentile_paths.p95[d],
  }));
  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-950 p-4 space-y-4">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm uppercase tracking-wider text-neutral-400">
          Monte Carlo VaR
        </h3>
        <span className="text-xs text-neutral-500">
          {data.n_simulations.toLocaleString()} paths · 1Y horizon
        </span>
      </div>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
            <defs>
              <linearGradient id="mc-band" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#5eead4" stopOpacity={0.35} />
                <stop offset="100%" stopColor="#5eead4" stopOpacity={0.05} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#262626" strokeDasharray="3 3" />
            <XAxis dataKey="day" tick={{ fill: "#a3a3a3", fontSize: 11 }} stroke="#404040" />
            <YAxis tick={{ fill: "#a3a3a3", fontSize: 11 }} stroke="#404040" />
            <Tooltip
              contentStyle={{ background: "#0a0a0a", border: "1px solid #262626", fontSize: 12 }}
              formatter={(v) => (typeof v === "number" ? v.toFixed(1) : v)}
            />
            <Legend wrapperStyle={{ fontSize: 12, color: "#cbd5e1" }} />
            <Area type="monotone" dataKey="p95" stroke="transparent" fill="url(#mc-band)" />
            <Area type="monotone" dataKey="p75" stroke="transparent" fill="url(#mc-band)" />
            <Area type="monotone" dataKey="p25" stroke="transparent" fill="url(#mc-band)" />
            <Area type="monotone" dataKey="p05" stroke="transparent" fill="url(#mc-band)" />
            <Line type="monotone" dataKey="p50" stroke="#5eead4" strokeWidth={2} dot={false} name="median" />
            <Line type="monotone" dataKey="p95" stroke="#a3a3a3" strokeWidth={1} dot={false} name="95th" />
            <Line type="monotone" dataKey="p05" stroke="#a3a3a3" strokeWidth={1} dot={false} name="5th" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <StatPill label="VaR 95%" value={pct(data.var_95)} tone="warn" />
        <StatPill label="VaR 99%" value={pct(data.var_99)} tone="warn" />
        <StatPill label="CVaR 95%" value={pct(data.cvar_95)} tone="bad" />
        <StatPill label="CVaR 99%" value={pct(data.cvar_99)} tone="bad" />
      </div>
      <div>
        <h4 className="text-xs uppercase tracking-wider text-neutral-500 mb-2">
          Probability of loss exceeding…
        </h4>
        <div className="grid grid-cols-3 gap-2">
          <StatPill label="> 10%" value={pct(data.p_loss_10)} tone="warn" />
          <StatPill label="> 20%" value={pct(data.p_loss_20)} tone="warn" />
          <StatPill label="> 30%" value={pct(data.p_loss_30)} tone="bad" />
        </div>
      </div>
    </div>
  );
}

// ---------- Stress tests ----------

function StressSection({ scenarios, onRunCustom, customResult, allowCustom = true }) {
  const [start, setStart] = useState("2018-12-01");
  const [end, setEnd] = useState("2019-01-31");
  const [name, setName] = useState("custom");
  const [running, setRunning] = useState(false);

  async function runCustom() {
    setRunning(true);
    try {
      await onRunCustom({ start, end, name });
    } finally {
      setRunning(false);
    }
  }

  function tone(ret) {
    if (ret === null || ret === undefined) return "text-neutral-500";
    if (ret < -0.3) return "text-rose-300 font-semibold";
    if (ret < -0.15) return "text-rose-400";
    if (ret < 0) return "text-amber-400";
    return "text-emerald-300";
  }

  const all = customResult ? [...scenarios, customResult] : scenarios;
  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-950 p-4 space-y-4">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm uppercase tracking-wider text-neutral-400">
          Historical Stress Tests
        </h3>
        <span className="text-xs text-neutral-500">
          current weights applied to historical windows
        </span>
      </div>
      <table className="w-full text-sm font-mono">
        <thead>
          <tr className="text-left text-neutral-400 border-b border-neutral-800">
            <th className="py-2 pr-3 font-sans font-medium">Scenario</th>
            <th className="py-2 pr-3 font-sans font-medium">Period</th>
            <th className="py-2 pr-3 font-sans font-medium text-right">Return</th>
            <th className="py-2 pr-3 font-sans font-medium text-right">Worst Day</th>
            <th className="py-2 pr-0 font-sans font-medium text-right">Max DD</th>
          </tr>
        </thead>
        <tbody>
          {all.map((s, i) => (
            <tr key={`${s.name}-${i}`} className="border-b border-neutral-900 last:border-b-0">
              <td className="py-2 pr-3 font-sans text-white">{s.name}</td>
              <td className="py-2 pr-3 text-xs text-neutral-400">
                {s.start} → {s.end}
              </td>
              <td className={`py-2 pr-3 text-right ${tone(s.portfolio_return)}`}>
                {pct(s.portfolio_return, 2)}
              </td>
              <td className={`py-2 pr-3 text-right ${tone(s.worst_day)}`}>
                {pct(s.worst_day, 2)}
              </td>
              <td className={`py-2 pr-0 text-right ${tone(s.max_drawdown)}`}>
                {pct(s.max_drawdown, 2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {allowCustom && (
        <div className="rounded-md border border-neutral-800 bg-black p-3 flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-neutral-500 mb-1">
              Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="bg-black border border-neutral-800 text-neutral-200 rounded px-2 py-1 text-sm w-40"
            />
          </div>
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-neutral-500 mb-1">
              Start
            </label>
            <input
              type="date"
              value={start}
              onChange={(e) => setStart(e.target.value)}
              className="bg-black border border-neutral-800 text-neutral-200 rounded px-2 py-1 text-sm"
            />
          </div>
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-neutral-500 mb-1">
              End
            </label>
            <input
              type="date"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              className="bg-black border border-neutral-800 text-neutral-200 rounded px-2 py-1 text-sm"
            />
          </div>
          <button
            type="button"
            onClick={runCustom}
            disabled={running}
            className="ml-auto rounded-md bg-white px-3 py-1.5 text-sm font-medium text-black hover:bg-neutral-200 disabled:opacity-60"
          >
            {running ? "Running…" : "Run custom"}
          </button>
        </div>
      )}
    </div>
  );
}

// ---------- GARCH ----------

function GarchSection({ data }) {
  if (!data) return null;
  const history = data.history.map((h) => ({
    date: h.date,
    realised: h.realised,
    garch: h.garch,
  }));
  const lastHistDate = history[history.length - 1]?.date;
  const forward = data.forward.map((f, i) => ({
    date: `+${f.day}d`,
    forecast: f.forecast,
    low: f.low,
    high: f.high,
  }));

  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-950 p-4 space-y-4">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm uppercase tracking-wider text-neutral-400">
          GARCH(1,1) Volatility
        </h3>
        <span className="text-xs text-neutral-500">
          per-asset fit, weighted via correlation matrix
        </span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <StatPill label="Realised vol" value={pct(data.historical_vol)} tone="neutral" />
        <StatPill label="30d forecast" value={pct(data.forecast_vol)} tone={data.forecast_vol > data.historical_vol ? "warn" : "good"} />
        <StatPill label="Band low" value={pct(data.forecast_band_low)} tone="neutral" />
        <StatPill label="Band high" value={pct(data.forecast_band_high)} tone="neutral" />
      </div>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={history} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
            <CartesianGrid stroke="#262626" strokeDasharray="3 3" />
            <XAxis dataKey="date" tick={{ fill: "#a3a3a3", fontSize: 11 }} stroke="#404040" minTickGap={48} />
            <YAxis tick={{ fill: "#a3a3a3", fontSize: 11 }} stroke="#404040" tickFormatter={(v) => pct(v)} />
            <Tooltip
              contentStyle={{ background: "#0a0a0a", border: "1px solid #262626", fontSize: 12 }}
              formatter={(v) => pct(v, 1)}
            />
            <Legend wrapperStyle={{ fontSize: 12, color: "#cbd5e1" }} />
            <Line type="monotone" dataKey="realised" stroke="#a3a3a3" dot={false} strokeWidth={1.5} name="21d realised" />
            <Line type="monotone" dataKey="garch" stroke="#5eead4" dot={false} strokeWidth={1.5} name="GARCH cond." />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="h-44">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={forward} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
            <defs>
              <linearGradient id="g-band" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#facc15" stopOpacity={0.35} />
                <stop offset="100%" stopColor="#facc15" stopOpacity={0.05} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#262626" strokeDasharray="3 3" />
            <XAxis dataKey="date" tick={{ fill: "#a3a3a3", fontSize: 11 }} stroke="#404040" />
            <YAxis tick={{ fill: "#a3a3a3", fontSize: 11 }} stroke="#404040" tickFormatter={(v) => pct(v)} />
            <Tooltip
              contentStyle={{ background: "#0a0a0a", border: "1px solid #262626", fontSize: 12 }}
              formatter={(v) => pct(v, 1)}
            />
            <Area type="monotone" dataKey="high" stroke="transparent" fill="url(#g-band)" />
            <Area type="monotone" dataKey="low" stroke="transparent" fill="url(#g-band)" />
            <Line type="monotone" dataKey="forecast" stroke="#facc15" dot={false} strokeWidth={2} name="forecast" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <div>
        <h4 className="text-xs uppercase tracking-wider text-neutral-500 mb-2">
          Per-asset parameters
          {data.persistent_assets.length > 0 && (
            <span className="ml-2 inline-flex items-center rounded-full border border-amber-900 bg-amber-950/50 px-2 py-0.5 text-[10px] font-medium text-amber-300">
              persistence α+β &gt; 0.95 on {data.persistent_assets.join(", ")}
            </span>
          )}
        </h4>
        <table className="w-full text-xs font-mono">
          <thead>
            <tr className="text-left text-neutral-500 border-b border-neutral-800">
              <th className="py-1 pr-3 font-sans">Ticker</th>
              <th className="py-1 pr-3 font-sans text-right">α</th>
              <th className="py-1 pr-3 font-sans text-right">β</th>
              <th className="py-1 pr-3 font-sans text-right">ω</th>
              <th className="py-1 pr-3 font-sans text-right">α+β</th>
              <th className="py-1 pr-0 font-sans text-right">Fcst Vol</th>
            </tr>
          </thead>
          <tbody>
            {data.assets.map((a) => (
              <tr key={a.ticker} className="border-b border-neutral-900 last:border-b-0">
                <td className="py-1 pr-3 font-sans text-white">{a.ticker}</td>
                <td className="py-1 pr-3 text-right">{a.alpha.toFixed(3)}</td>
                <td className="py-1 pr-3 text-right">{a.beta.toFixed(3)}</td>
                <td className="py-1 pr-3 text-right">{a.omega.toExponential(2)}</td>
                <td className={`py-1 pr-3 text-right ${a.persistent ? "text-amber-300" : "text-neutral-300"}`}>
                  {(a.alpha + a.beta).toFixed(3)}
                </td>
                <td className="py-1 pr-0 text-right">{pct(a.forecast_annual_vol)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StatPill({ label, value, tone = "neutral" }) {
  const tones = {
    neutral: "text-white",
    good: "text-emerald-300",
    warn: "text-amber-300",
    bad: "text-rose-300",
  };
  return (
    <div className="rounded-lg border border-neutral-800 bg-black px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-neutral-400">{label}</div>
      <div className={`font-mono text-sm font-semibold mt-0.5 ${tones[tone]}`}>{value}</div>
    </div>
  );
}

// ---------- Tab root ----------

export default function RiskTab() {
  const [mc, setMc] = useState(null);
  const [stress, setStress] = useState(null);
  const [customStress, setCustomStress] = useState(null);
  const [garchData, setGarchData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([getMonteCarlo(), getStressTests(), getGarch()])
      .then(([m, s, g]) => {
        if (cancelled) return;
        setMc(m);
        setStress(s.scenarios);
        setGarchData(g);
      })
      .catch((e) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  async function runCustom(payload) {
    const res = await postCustomStress(payload);
    setCustomStress(res);
  }

  const commentaryMetrics = useMemo(() => {
    if (!mc && !stress && !garchData) return null;
    return {
      monte_carlo: mc,
      stress_tests: stress,
      garch: garchData,
    };
  }, [mc, stress, garchData]);

  if (loading) {
    return (
      <div className="text-sm text-neutral-500 p-6">
        Running risk models (Monte Carlo + stress replay + GARCH fits)…
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

  return (
    <div className="space-y-4">
      <MonteCarloSection data={mc} />
      <StressSection
        scenarios={stress ?? []}
        customResult={customStress}
        onRunCustom={runCustom}
        allowCustom={!IS_STATIC}
      />
      <GarchSection data={garchData} />
      <CommentaryButton
        module="risk"
        metrics={commentaryMetrics}
        label="Generate AI Commentary"
      />
    </div>
  );
}
