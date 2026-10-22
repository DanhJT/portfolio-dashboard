import React from "react";
import { SERIES } from "../../chartTheme.js";
import { UNIVERSE_AS_OF, UNIVERSE_SIZE } from "../../sectors.js";

// Keep in step with backend/services/strategy.py and backend/scheduler.py.
const RULES = [
  {
    rule: "Universe",
    setting: `S&P 500 (${UNIVERSE_SIZE} listings)`,
    why: "The standard US large-cap benchmark, so the selection is defined by index membership rather than by hand. Deep liquidity and reliable data keep trading costs and data errors low.",
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
    setting: "Book-to-market",
    why: "Cheap stocks relative to book value have historically earned a premium (Fama & French, 1992).",
  },
  {
    rule: "Outlier clip",
    setting: "±3σ",
    why: "Stops one extreme reading from dominating the ranking.",
  },
  {
    rule: "Holdings",
    setting: "Top 15, score-weighted",
    why: "Tilts toward the strongest signals while staying diversified. A floor keeps the lowest-ranked name a meaningful position.",
  },
  {
    rule: "Position cap",
    setting: "35% per stock",
    why: "Limits single-stock risk. Any excess is spread across the other holdings.",
  },
  {
    rule: "Frequency",
    setting: "Monthly: first US trading day, 09:30 ET",
    why: "Momentum signals fade within months. Monthly rebalancing keeps them fresh without the turnover cost of trading more often.",
  },
  {
    rule: "Fallback",
    setting: "Momentum-only, then equal-weight",
    why: "If data fails, the portfolio is still defined, so it never stops for lack of data.",
  },
];

const LIMITS = [
  "15 names from the S&P 500 can still be sector-heavy (see Sector Exposure).",
  `The universe is index membership as of ${UNIVERSE_AS_OF}, refreshed by hand, so it is not point-in-time.`,
  "The value signal uses current price-to-book only.",
  "Transaction costs and taxes are not modeled.",
  "Educational use only, not investment advice.",
];

const REFERENCES = [
  { authors: "Evans, J. & Archer, S. (1968).", title: "Diversification and the Reduction of Dispersion: An Empirical Analysis.", journal: "Journal of Finance, 23(5)." },
  { authors: "Fama, E. & French, K. (1993).", title: "Common Risk Factors in the Returns on Stocks and Bonds.", journal: "Journal of Financial Economics, 33(1)." },
  { authors: "Asness, C., Moskowitz, T. & Pedersen, L. (2013).", title: "Value and Momentum Everywhere.", journal: "Journal of Finance, 68(3)." },
  { authors: "Jegadeesh, N. & Titman, S. (1993).", title: "Returns to Buying Winners and Selling Losers.", journal: "Journal of Finance, 48(1)." },
  { authors: "Fama, E. & French, K. (1992).", title: "The Cross-Section of Expected Stock Returns.", journal: "Journal of Finance, 47(2)." },
  { authors: "Jegadeesh, N. (1990).", title: "Evidence of Predictable Behavior of Security Returns.", journal: "Journal of Finance, 45(3)." },
];

const FALLBACK_STRATEGIES = new Set(["momentum", "equal-weight-fallback"]);

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

function StatusStrip({ portfolio, strategyLabels }) {
  const label = portfolio
    ? strategyLabels[portfolio.strategy] ?? portfolio.strategy
    : "—";
  const rebalanced = portfolio?.rebalanced_at
    ? new Date(portfolio.rebalanced_at).toLocaleDateString()
    : "—";
  const tickers = portfolio?.tickers ?? [];

  return (
    <div className="panel px-4 py-2.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px]">
      <span className="text-xs uppercase tracking-wider text-neutral-400">About this portfolio</span>
      <span className="text-emerald-300">{label}</span>
      <span className="text-neutral-400">
        {tickers.length ? `${tickers.length} holdings: ` : "—"}
        <span className="font-mono text-neutral-300">{tickers.join(" · ")}</span>
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

export default function AboutTab({ portfolio, strategyLabels = {} }) {
  return (
    <div className="space-y-3">
      <StatusStrip portfolio={portfolio} strategyLabels={strategyLabels} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 items-start">
        {/* Left: what it is, how it picks, what it doesn't do */}
        <div className="space-y-3">
          <section className="panel p-4">
            <Heading>The strategy</Heading>
            <p className="text-[13px] text-neutral-300 leading-relaxed">
              This is a systematic, long-only US equity portfolio. Each month it ranks every
              stock in the S&amp;P 500 on <em>value</em> and <em>momentum</em>, holds the 15
              highest-scoring names, and sizes each position by its score. Stocks are chosen
              by rules, not by hand.
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
                <span><span className="text-white">Value:</span> book-to-market, which is 1 ÷ price-to-book.</span>
              </li>
              <li className="flex gap-2">
                <span className="font-mono text-neutral-500">3</span>
                <span>Each signal becomes a z-score across the universe, clipped at ±3σ, and the two are blended 50/50.</span>
              </li>
            </ol>
          </section>

          <section className="panel p-4">
            <Heading>Why 15 holdings</Heading>
            <p className="text-[13px] text-neutral-300 leading-relaxed">
              Around 10–15 stocks already capture most of the available benefit of
              diversification (Evans &amp; Archer, 1968), so 15 names keep returns driven by the
              factor tilt rather than single-stock news. Taking the top 15 of roughly 500 is a
              far sharper cut than the 30% breakpoint Fama &amp; French (1993) use to build their
              value factor: the tilt is more concentrated, and so is its tracking error.
            </p>
          </section>

          <section className="panel p-4">
            <Heading>Known limits</Heading>
            <ul className="space-y-1 text-[13px] text-neutral-300 leading-relaxed">
              {LIMITS.map((l) => (
                <li key={l} className="flex gap-2">
                  <Marker />
                  <span>{l}</span>
                </li>
              ))}
            </ul>
          </section>
        </div>

        {/* Right: the rules with their reasoning, then sources */}
        <div className="space-y-3">
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
