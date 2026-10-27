import React, { useEffect, useState } from "react";
import { getBacktest } from "../../api.js";
import { SERIES } from "../../chartTheme.js";
import { UNIVERSE_AS_OF, UNIVERSE_SIZE } from "../../sectors.js";

// Keep in step with backend/services/strategy.py and backend/services/fundamentals.py.
const RULES = [
  {
    rule: "Universe",
    setting: `S&P 500 (${UNIVERSE_SIZE} listings)`,
    why: "The standard US large-cap benchmark, so the selection is defined by index membership rather than by hand. A stock only counts from the date it joined the index.",
  },
  {
    rule: "Signal blend",
    setting: "50% value / 50% momentum",
    why: "The two factors are negatively correlated, so the combination is smoother than either one alone (Asness, Moskowitz & Pedersen, 2013).",
  },
  {
    rule: "Momentum window",
    setting: "12 months, skip latest 1",
    why: "Recent 3–12-month winners tend to keep outperforming (Jegadeesh & Titman, 1993). The last month is skipped because one-month returns tend to reverse (Jegadeesh, 1990).",
  },
  {
    rule: "Value measure",
    setting: "Book-to-market, SEC filings, 90-day lag",
    why: "Cheap stocks relative to book value have historically earned a premium (Fama & French, 1992). Book equity is only used once the filing would have been public.",
  },
  {
    rule: "Outlier clip",
    setting: "±3σ",
    why: "Stops one extreme reading from dominating the ranking.",
  },
  {
    rule: "Holdings",
    setting: "Top 10% of companies (min 10)",
    why: "A percentile cut scales with the universe and matches how the research builds factor portfolios. Today that is roughly 45–50 companies.",
  },
  {
    rule: "Weighting",
    setting: "Proportional to composite score",
    why: "Stronger signals get more money, without the extremes of concentrating on a few names.",
  },
  {
    rule: "Position cap",
    setting: "35% per stock",
    why: "A hard ceiling on single-stock risk. Any excess is spread across the other holdings.",
  },
  {
    rule: "Frequency",
    setting: "Monthly: first US trading day",
    why: "Momentum signals fade within months. Monthly rebalancing keeps them fresh without the turnover cost of trading more often.",
  },
  {
    rule: "Fallback",
    setting: "Momentum-only if value data is thin",
    why: "If fewer than half the ranked stocks have value data, that month ranks on momentum alone rather than on a biased subset.",
  },
];

const REFERENCES = [
  { authors: "Asness, C., Moskowitz, T. & Pedersen, L. (2013).", title: "Value and Momentum Everywhere.", journal: "Journal of Finance, 68(3)." },
  { authors: "Jegadeesh, N. & Titman, S. (1993).", title: "Returns to Buying Winners and Selling Losers.", journal: "Journal of Finance, 48(1)." },
  { authors: "Fama, E. & French, K. (1992).", title: "The Cross-Section of Expected Stock Returns.", journal: "Journal of Finance, 47(2)." },
  { authors: "Fama, E. & French, K. (1993).", title: "Common Risk Factors in the Returns on Stocks and Bonds.", journal: "Journal of Financial Economics, 33(1)." },
  { authors: "Jegadeesh, N. (1990).", title: "Evidence of Predictable Behavior of Security Returns.", journal: "Journal of Finance, 45(3)." },
  { authors: "Statman, M. (1987).", title: "How Many Stocks Make a Diversified Portfolio?", journal: "Journal of Financial and Quantitative Analysis, 22(3)." },
  { authors: "Evans, J. & Archer, S. (1968).", title: "Diversification and the Reduction of Dispersion: An Empirical Analysis.", journal: "Journal of Finance, 23(5)." },
];

const FALLBACK_STRATEGIES = new Set(["momentum", "equal-weight-fallback"]);
const STATUS_TICKERS = 8;
const RECENT_REBALANCES = 12;
// Assumed one-way trading cost for the cost estimate in Known limits.
const COST_BPS = 10;

const pct = (v, d = 1) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : `${(v * 100).toFixed(d)}%`;
const fmtDate = (iso) =>
  iso ? new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }) : "—";

function Heading({ children }) {
  return (
    <h2 className="text-xs uppercase tracking-wider text-neutral-400 mb-2">{children}</h2>
  );
}

function Marker() {
  return (
    <span
      className="mt-[7px] inline-block h-1.5 w-1.5 shrink-0 rounded-full"
      style={{ background: SERIES.portfolio }}
      aria-hidden
    />
  );
}

function Stat({ label, value }) {
  return (
    <div className="panel-raise px-2.5 py-1.5 min-w-0">
      <div className="text-[9px] uppercase tracking-wider text-neutral-500">{label}</div>
      <div className="font-mono text-sm text-neutral-100 mt-0.5">{value}</div>
    </div>
  );
}

function StatusStrip({ portfolio, strategyLabels }) {
  const label = portfolio
    ? strategyLabels[portfolio.strategy] ?? portfolio.strategy
    : "—";
  const rebalanced = portfolio?.rebalanced_at
    ? new Date(portfolio.rebalanced_at).toLocaleDateString()
    : "—";
  const tickers = portfolio?.tickers ?? [];
  const shown = tickers.slice(0, STATUS_TICKERS);
  const more = tickers.length - shown.length;

  return (
    <div className="panel px-4 py-2.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px]">
      <span className="text-xs uppercase tracking-wider text-neutral-400">About this portfolio</span>
      <span className="text-emerald-300">{label}</span>
      <span className="text-neutral-400" title={tickers.join(" · ")}>
        {tickers.length ? `${tickers.length} holdings, largest: ` : "—"}
        <span className="font-mono text-neutral-300">{shown.join(" · ")}</span>
        {more > 0 && <span className="text-neutral-500"> +{more} more</span>}
      </span>
      <span className="font-mono text-neutral-400">Rebalanced {rebalanced}</span>
      {portfolio && FALLBACK_STRATEGIES.has(portfolio.strategy) && (
        <span className="text-amber-300">
          Fallback active: value data unavailable at last rebalance
        </span>
      )}
    </div>
  );
}

function BacktestPanel({ backtest }) {
  if (!backtest) {
    return (
      <section className="panel p-4">
        <Heading>Backtest</Heading>
        <p className="text-[13px] text-neutral-400">Backtest details load from the daily snapshot.</p>
      </section>
    );
  }
  const s = backtest.summary;
  const last = backtest.rebalances[backtest.rebalances.length - 1];
  return (
    <section className="panel p-4 space-y-3">
      <Heading>Backtest</Heading>
      <p className="text-[13px] text-neutral-300 leading-relaxed">
        The performance figures on the Overview tab are a backtest of these rules, not a replay of
        today&apos;s holdings. On the first trading day of every month since{" "}
        <span className="text-white">{fmtDate(backtest.start)}</span>, the strategy re-ranked the
        index using only data from before that day, bought the new top 10%, and let the weights
        drift with prices until the next month. Returns include dividends and are before trading
        costs and taxes. Today&apos;s holdings are simply the latest of these rebalances.
      </p>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <Stat label="Rebalances" value={s.rebalances} />
        <Stat label="Avg holdings" value={s.avg_holdings} />
        <Stat label="Avg monthly turnover" value={pct(s.avg_turnover, 0)} />
        <Stat label="Value data coverage" value={pct(s.avg_value_coverage, 0)} />
      </div>
      {last && (
        <p className="text-[12px] text-neutral-400 leading-snug">
          <span className="text-neutral-200">Last rebalance {fmtDate(last.date)}:</span>{" "}
          {last.n_holdings} holdings, {pct(last.turnover, 0)} turnover.
          {last.added.length > 0 && (
            <> Added <span className="font-mono text-emerald-300">{last.added.join(" ")}</span>.</>
          )}
          {last.removed.length > 0 && (
            <> Sold <span className="font-mono text-rose-300">{last.removed.join(" ")}</span>.</>
          )}
        </p>
      )}
    </section>
  );
}

function RecentRebalances({ backtest }) {
  if (!backtest?.rebalances?.length) return null;
  const rows = backtest.rebalances.slice(-RECENT_REBALANCES).reverse();
  return (
    <section className="panel p-4">
      <Heading>Recent rebalances</Heading>
      <table className="w-full text-[12px]">
        <thead>
          <tr className="text-neutral-500 border-b rule text-left">
            <th className="font-normal pb-1 pr-3">Date</th>
            <th className="font-normal pb-1 pr-3 text-right">Holdings</th>
            <th className="font-normal pb-1 pr-3 text-right">In / out</th>
            <th className="font-normal pb-1 pr-3 text-right">Turnover</th>
            <th className="font-normal pb-1 text-right">Largest</th>
          </tr>
        </thead>
        <tbody className="font-mono text-[11px]">
          {rows.map((r) => (
            <tr key={r.date} className="border-b rule last:border-b-0">
              <td className="py-1 pr-3 font-sans text-neutral-300">
                {fmtDate(r.date)}
                {r.strategy !== "value-momentum" && (
                  <span className="ml-1.5 text-[10px] text-amber-300">momentum-only</span>
                )}
              </td>
              <td className="py-1 pr-3 text-right text-neutral-300">{r.n_holdings}</td>
              <td className="py-1 pr-3 text-right">
                <span className="text-emerald-300">+{r.added.length}</span>{" "}
                <span className="text-rose-300">−{r.removed.length}</span>
              </td>
              <td className="py-1 pr-3 text-right text-neutral-300">{pct(r.turnover, 0)}</td>
              <td className="py-1 text-right text-neutral-400">{pct(r.max_weight, 1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export default function AboutTab({ portfolio, strategyLabels = {} }) {
  const [backtest, setBacktest] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getBacktest()
      .then((b) => { if (!cancelled) setBacktest(b); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const summary = backtest?.summary;
  const largestEver = summary ? pct(summary.max_weight_ever, 1) : "about 3%";
  // One-way turnover t means buying t and selling t each month.
  const annualCost = summary?.avg_turnover != null
    ? summary.avg_turnover * 2 * 12 * (COST_BPS / 10000)
    : null;

  const limits = [
    `The universe is today's index (as of ${UNIVERSE_AS_OF}). Stocks only count from the date they joined, but companies that have since been removed are missing. That flatters past returns: in a check in October 2026, an equal-weight basket of this universe beat the real equal-weight S&P 500 ETF (RSP) by about 3 percentage points a year. Read the backtest as optimistic.`,
    "SEC data shows the latest version of each filing, so a later restatement can slip into an earlier month.",
    annualCost != null
      ? `Trading costs and taxes are not modeled. At ${COST_BPS} bps per trade, the average turnover would cost roughly ${pct(annualCost, 1)} a year.`
      : "Trading costs and taxes are not modeled.",
    "Signals use the close before each rebalance, and trades are assumed to fill at that price.",
    "Educational use only, not investment advice.",
  ];

  return (
    <div className="space-y-3">
      <StatusStrip portfolio={portfolio} strategyLabels={strategyLabels} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 items-start">
        {/* Left: what it is, how it picks, why these settings, what it doesn't do */}
        <div className="space-y-3">
          <section className="panel p-4">
            <Heading>The strategy</Heading>
            <p className="text-[13px] text-neutral-300 leading-relaxed">
              This is a systematic, long-only US equity portfolio. Each month it ranks every
              stock in the S&amp;P 500 on <em>value</em> and <em>momentum</em>, holds the top 10%
              of companies (about 45–50 names), and weights each one in proportion to its score.
              Stocks are chosen by rules, not by hand.
            </p>
          </section>

          <section className="panel p-4">
            <Heading>How a stock is picked</Heading>
            <ol className="space-y-1.5 text-[13px] text-neutral-300 leading-relaxed">
              <li className="flex gap-2">
                <span className="font-mono text-neutral-500">1</span>
                <span><span className="text-white">Momentum:</span> return over the past 12 months, skipping the most recent month.</span>
              </li>
              <li className="flex gap-2">
                <span className="font-mono text-neutral-500">2</span>
                <span><span className="text-white">Value:</span> book-to-market. Book equity comes from the company&apos;s latest quarterly SEC filing that is at least 90 days old. Market value is shares outstanding × price.</span>
              </li>
              <li className="flex gap-2">
                <span className="font-mono text-neutral-500">3</span>
                <span>Each signal becomes a z-score across the universe, clipped at ±3σ, and the two are blended 50/50.</span>
              </li>
              <li className="flex gap-2">
                <span className="font-mono text-neutral-500">4</span>
                <span>The top 10% of companies by blended score are bought. Where a company has two share classes (GOOGL/GOOG), only the higher-scoring one counts.</span>
              </li>
            </ol>
          </section>

          <section className="panel p-4">
            <Heading>Why the top 10%</Heading>
            <p className="text-[13px] text-neutral-300 leading-relaxed">
              Momentum research sorts stocks into deciles and studies the top one (Jegadeesh &amp;
              Titman, 1993), so a 10% cut follows the standard construction. A percentile also
              keeps the rule the same if the universe grows or shrinks, where a fixed count would
              not. At about 45–50 names the portfolio holds enough stocks to diversify away most
              company-specific risk (Statman, 1987, puts the threshold at 30–40 stocks), while
              staying concentrated enough that returns are driven by the value and momentum tilt.
            </p>
          </section>

          <section className="panel p-4">
            <Heading>Why a 35% cap</Heading>
            <p className="text-[13px] text-neutral-300 leading-relaxed">
              Score weighting gives the strongest signals more money, so the cap puts a hard
              ceiling on how much any one company can matter. However strong its score, no single
              fraud, failed product or data error can sink more than about a third of the portfolio.
            </p>
            <p className="text-[13px] text-neutral-300 leading-relaxed mt-2">
              In normal months the cap does not bind: spread across about 50 names, the largest
              position in the backtest never exceeded{" "}
              <span className="font-mono text-white">{largestEver}</span>. It is there as a guardrail
              for abnormal months. If missing data shrinks the ranked list, or the portfolio
              falls back to a short list of names, the cap stops one stock from dominating.
            </p>
          </section>

          <section className="panel p-4">
            <Heading>Known limits</Heading>
            <ul className="space-y-1 text-[13px] text-neutral-300 leading-relaxed">
              {limits.map((l) => (
                <li key={l} className="flex gap-2">
                  <Marker />
                  <span>{l}</span>
                </li>
              ))}
            </ul>
          </section>
        </div>

        {/* Right: backtest, the rules with their reasoning, then sources */}
        <div className="space-y-3">
          <BacktestPanel backtest={backtest} />

          <section className="panel p-4">
            <Heading>Rebalance rules</Heading>
            <div className="overflow-x-auto">
              <table className="w-full text-[12px] min-w-[520px]">
                <thead>
                  <tr className="text-neutral-500 border-b rule text-left">
                    <th className="font-normal pb-1 pr-3">Rule</th>
                    <th className="font-normal pb-1 pr-3">Setting</th>
                    <th className="font-normal pb-1">Why</th>
                  </tr>
                </thead>
                <tbody>
                  {RULES.map((r) => (
                    <tr key={r.rule} className="border-b rule last:border-b-0 align-top">
                      <td className="py-1.5 pr-3 text-neutral-200 whitespace-nowrap">{r.rule}</td>
                      <td className="py-1.5 pr-3 font-mono text-[11px] text-neutral-300">{r.setting}</td>
                      <td className="py-1.5 text-neutral-400 leading-snug">{r.why}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <RecentRebalances backtest={backtest} />

          <section className="panel p-4">
            <Heading>References</Heading>
            <ul className="space-y-1 text-[12px] text-neutral-400 leading-snug">
              {REFERENCES.map((ref) => (
                <li key={ref.title}>
                  {ref.authors} <span className="text-neutral-200">{ref.title}</span>{" "}
                  <em>{ref.journal}</em>
                </li>
              ))}
            </ul>
          </section>
        </div>
      </div>
    </div>
  );
}
