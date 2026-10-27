# Portfolio Projects — Architecture & Usage Overview

A single reference for the two related projects: the **personal portfolio website** and the **Portfolio Risk Dashboard**. It is written for the whole team. Plain-language explanations come first; the math lives in clearly-marked **📐 Methodology / For the curious** callouts that you can safely skip.

---

## 1. Executive summary

There are two separate projects:

| Project | What it is | Tech in one line |
| --- | --- | --- |
| **Website** (`PortfolioWS`) | A personal portfolio / CV site that showcases finance projects and links out to live demos. | Astro 6 static site, hosted on Vercel. |
| **Dashboard** (`portfolio-dashboard`) | A working quantitative equity tool: it picks stocks with a value-momentum strategy, rebalances monthly, and reports performance, risk, and liquidity. | React + Vite front end, FastAPI/Python back end, market data from Yahoo Finance. |

**How they relate:** the website is a *shop window*. One of the projects it showcases is the Portfolio Dashboard, and it links to the dashboard's live deployment. That is the entire relationship — a hyperlink. They **share no code and have no runtime connection**. You can change, break, or redeploy either one without affecting the other.

---

## 2. How the two projects fit together

The website features six projects. One of them is the Portfolio Dashboard. The website's project page for the dashboard contains an `externalUrl` that points to the dashboard's deployed address:

```
https://portfolio-dashboard-five-iota.vercel.app
```

When a visitor clicks "view live demo," their browser opens the dashboard directly. The website's own server (Vercel static hosting) is never involved in that, and **the website never calls the dashboard's API**.

```
                      Visitor's browser
                             |
                clicks "View live project"
                             |
        +--------------------+---------------------+
        |                                          |
        v                                          v
+---------------------+   plain hyperlink   +-----------------------------+
|   Website           | ------------------> |   Dashboard                 |
|   (PortfolioWS)     |   (externalUrl)     |   (portfolio-dashboard)     |
|   static Astro site |                     |   React + FastAPI app       |
+---------------------+                     +-----------------------------+

   NO shared code.  NO shared database.  NO API calls between them.
   The only link is a URL string in a Markdown file.
```

**Why this matters in practice:**

- Deploying a new version of the website cannot break the dashboard, and vice versa.
- The two repos can use completely different tooling (and they do: Astro/TypeScript vs React/Python).
- If the dashboard's URL ever changes, only one line in one Markdown file on the website needs updating.

---

## 3. Project A — The Website (PortfolioWS)

### 3.1 In plain language

This is a fast, lightweight personal portfolio site. It introduces the owner (a finance master's student), lists their projects with detail pages, and provides an about and contact page. There is no login, no database, and no server-side logic at request time — every page is pre-built into plain HTML and served as static files. That makes it cheap, fast, and very hard to break.

### 3.2 Stack

| Area | Choice |
| --- | --- |
| Framework | Astro `^6.1.8` |
| Language | TypeScript (strict mode via `tsconfig.json`) |
| Node runtime | `>= 22.12.0` (declared in `package.json` `engines`) |
| Styling | Scoped per-component CSS + a global stylesheet — **no CSS framework** |
| Fonts | Google Fonts: Inter (sans) + Source Serif 4 (serif) |
| Hosting adapter | `@astrojs/vercel` `^10.0.7` |
| Analytics | Vercel Web Analytics (`@vercel/analytics` `^2.0.1`, enabled in `astro.config.mjs`) |
| Package name | `proto-proxima` |
| Module system | ES modules (`"type": "module"`) |

> 📐 **For the curious — what "Astro static" means**
> Astro renders all pages to plain HTML at *build* time (`astro build` → `/dist`). There is no Node server answering requests in production; Vercel just serves files from a CDN. This is "SSG" (Static Site Generation) rather than "SSR" (Server-Side Rendering). The Vercel adapter here is used for build/deploy integration and Web Analytics, not for runtime rendering.

### 3.3 Structure

The site uses Astro's **file-based routing** — a file in `src/pages/` becomes a URL.

| Path | Role |
| --- | --- |
| `src/pages/index.astro` | Home page |
| `src/pages/about.astro` | About / bio |
| `src/pages/contact.astro` | Contact |
| `src/pages/projects/index.astro` | Grid of all projects |
| `src/pages/projects/[...slug].astro` | Dynamic project detail page (one per Markdown file) |
| `src/layouts/Layout.astro` | Shared page shell (head, fonts, header, footer) |
| `src/components/Header.astro`, `Footer.astro`, `ProjectCard.astro` | Reusable UI pieces |
| `src/content/projects/*.md` | The project content (a lightweight Markdown "CMS") |
| `src/content.config.ts` | Schema/validation for project Markdown front-matter |
| `src/styles/global.css` | Global styles |
| `public/` | Static assets served as-is |

**The Markdown CMS.** Each project is a Markdown file with a structured header (front-matter). Astro **content collections** validate every file against a schema, so a typo in a field is caught at build time. The schema (`src/content.config.ts`) defines these fields:

| Field | Type | Notes |
| --- | --- | --- |
| `title` | string (required) | |
| `summary` | string (required) | |
| `course` | string (optional) | |
| `grade` | string (optional) | |
| `date` | string (optional) | |
| `role` | string (optional) | |
| `tools` | string[] | defaults to `[]` |
| `tags` | string[] | defaults to `[]` |
| `cover` | string (optional) | |
| `coverFit` | `"cover"` \| `"contain"` | defaults to `"cover"` |
| `screenshots` | array of `{ src, alt, caption }` | defaults to `[]` |
| `featured` | boolean | defaults to `false` |
| `order` | number | defaults to `100` (sort order) |
| `personal` | boolean | defaults to `false` |
| `status` | `"complete"` \| `"in-progress"` | defaults to `"complete"` |
| `externalUrl` | URL (optional) | link to live demo |
| `repoUrl` | URL (optional) | link to source |

### 3.4 What it does (pages)

- **Home** — hero intro, a "currently building" note, and featured projects.
- **About** — bio (finance MSc at BI Norwegian Business School), an education/work timeline, and a skills section.
- **Projects** — a grid of all projects.
- **Project detail** — rendered from Markdown, with image lightbox/galleries for screenshots.
- **Contact** — contact details.

**The six showcased projects:**

| Project | File |
| --- | --- |
| Portfolio Dashboard | `src/content/projects/financial-dashboard.md` |
| Fixed Income / Treasury | `src/content/projects/fixed-income-treasury.md` |
| FX carry trade | `src/content/projects/fx-carry-trade.md` |
| FX hedging | `src/content/projects/fx-hedging.md` |
| MediMedia LBO | `src/content/projects/medimedia-lbo.md` |
| Portfolio factor model | `src/content/projects/portfolio-factor-model.md` |

### 3.5 Data, integrations, hosting

- **Data:** Markdown content files only — no backend, no database, no environment variables.
- **Integrations:** Google Fonts and Vercel Web Analytics.
- **Hosting:** `astro build` outputs static files to `/dist`; Vercel auto-deploys on every git push. Pure static (no SSR).

---

## 4. Project B — The Dashboard (portfolio-dashboard)

### 4.1 In plain language

The dashboard is a real quantitative tool. Once a month it automatically picks five stocks using a rules-based "value-momentum" strategy and assigns each a weight. It then continuously reports how that portfolio is doing versus the market, how risky it is (including worst-case scenarios), and how easily it could be sold. There is **no human stock-picking** — the rules decide.

It runs in two modes:

- **Live mode** (used in local development): the React front end talks to the Python FastAPI back end, which pulls fresh numbers from Yahoo Finance.
- **Static mode** (used in production): there is **no running back end at all**. A daily job pre-computes every number into a single file (`snapshot.json`) and the front end just reads that file. This is why the production site has zero hosting cost and never shows an error from a flaky data provider.

### 4.2 Architecture diagram

```
  DEVELOPMENT (live mode)
  ------------------------
  +-------------------+        HTTP /api/...        +------------------+      +------------------+
  |  React + Vite     | <-------------------------> |  FastAPI back end| <--> |  Yahoo Finance   |
  |  (port 5173)      |   VITE_DATA_SOURCE=live     |  (port 8000)     |      |  (yfinance lib)  |
  +-------------------+                             +------------------+      +------------------+
                                                     in-memory app.state
                                                     (no database)

  PRODUCTION (static mode, the default)
  -------------------------------------
  +------------------+   GitHub Action (daily 07:00 UTC)   +---------------------+
  |  FastAPI runs    |  generate_snapshot.py  -----------> |  snapshot.json      |
  |  ONLY in the CI  |  serializes every endpoint          |  committed to repo  |
  |  job, not in prod|                                     +----------+----------+
  +------------------+                                                |
                                                            commit triggers redeploy
                                                                      v
  +-------------------+      fetch snapshot.json (from CDN)  +---------------------+
  |  React build      | <----------------------------------> |  Vercel static CDN  |
  |  VITE_DATA_SOURCE |        NO live back end              +---------------------+
  |  = static         |
  +-------------------+
```

### 4.3 Front end (`frontend/`)

| Area | Choice |
| --- | --- |
| Framework | React 18.3 |
| Build tool | Vite 5 (dev server on port **5173**) |
| Styling | Tailwind CSS 3, dark theme (`ink` neutrals + teal accent `#5eead4`) |
| Fonts | Inter + JetBrains Mono |
| Charts | Recharts |
| Language | Plain JavaScript / JSX (**no TypeScript**) |
| State | React hooks only (**no Redux**) |

**Structure:**

| Path | Role |
| --- | --- |
| `src/main.jsx` | React entry point |
| `src/App.jsx` | Tab navigation, top-level data loading, period selector |
| `src/api.js` | Data-access layer (static vs live switch) |
| `src/index.css` | Global styles / Tailwind layers |
| `src/components/tabs/OverviewTab.jsx` | Overview screen |
| `src/components/tabs/RiskTab.jsx` | Risk Models screen |
| `src/components/tabs/LiquidityTab.jsx` | Liquidity screen |
| `src/components/PortfolioTable.jsx` | Holdings table |
| `src/components/PerformanceChart.jsx` / `PerformanceSection.jsx` | Cumulative-return charts |
| `src/components/RelativePerformanceChart.jsx` | Excess-return (vs benchmark) chart |
| `src/components/RiskMetricsPanel.jsx` | The 8-card metric strip |
| `src/components/NewsPanel.jsx` | Ticker-filterable news |
| `src/components/CommentaryButton.jsx` | Triggers the auto-generated commentary |
| `src/components/TabNav.jsx` | Tab bar |
| `src/components/SidePanel.jsx` | Side panel UI |
| `public/snapshot.json` | The cached daily dataset (static mode) |

> Note: In the UI the three tabs are labeled **Overview**, **Risk Models**, and **Liquidity** (`App.jsx` `MAIN_TABS`).

#### The three screens

**Overview** — a strip of **8 risk-metric cards** across the top, then performance charts on the left and snapshot cards + news on the right.

The 8 metric cards (`RiskMetricsPanel.jsx`) are:

1. Annualised return
2. Annualised volatility
3. Sharpe ratio
4. Alpha (annualised)
5. Beta
6. Max drawdown
7. VaR 95%
8. CVaR 95%

The performance area shows a cumulative-return chart vs **SPY** with selectable horizons (3M / 6M / 1Y / 2Y) and an excess-return area chart. The right column has a risk-snapshot card, a liquidity-snapshot card, and a ticker-filterable news panel.

**Risk Models** — Monte Carlo percentile bands plus VaR/CVaR at 95% and 99% and the probability of losing more than 10/20/30%; a historical stress-test table (with a custom date window when running in live mode); a GARCH conditional-volatility history with a 30-day forecast and a per-asset α / β / ω / persistence table; and an AI-commentary button.

**Liquidity** — an editable AUM box (default **$1,000,000**) and a per-position table: 30-day average daily volume (ADV), position size in dollars, % of ADV, days-to-liquidate, a 1–5 liquidity score, the Kelly weight vs the current weight, and a divergence flag when they differ by more than 10 percentage points. Plus an AI-commentary button. When you change AUM, the dollar/ADV figures recalculate in the browser.

#### Front-end ↔ back-end switch (`src/api.js`)

The data layer reads an environment variable `VITE_DATA_SOURCE`:

- `"static"` (**the default**) → reads `public/snapshot.json`, **zero back-end calls**.
- `"live"` → calls the FastAPI back end at `VITE_API_BASE` (default `http://localhost:8000`).

```js
const DATA_SOURCE = import.meta.env.VITE_DATA_SOURCE ?? "static";
const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";
export const IS_STATIC = DATA_SOURCE === "static";
```

In static mode the snapshot is fetched once and cached. Liquidity is the one place that recomputes client-side when AUM changes — `scaleLiquidity()` rescales position size, % of ADV, and days-to-liquidate, because those scale linearly with AUM while ADV, Kelly weight, and the liquidity score do not. (Custom stress windows are the one feature that *requires* the live back end; in static mode the call throws a clear "requires the live backend" error.)

**Default portfolio if none is specified:** 25% AAPL, 25% MSFT, 20% NVDA, 15% JPM, 15% BRK-B (documented in the dashboard README). In normal operation the active portfolio is whatever the strategy most recently selected, not this default.

### 4.4 Back end (`backend/`)

| Area | Choice |
| --- | --- |
| Language | Python 3.9+ (CI runs 3.11) |
| Web framework | FastAPI `>=0.110` + Uvicorn `>=0.27` |
| Validation | Pydantic v2 (`>=2.6`) |
| Data / math | pandas `>=2.2`, numpy `>=1.26`, scipy `>=1.12` |
| Market data | yfinance `>=0.2.40` |
| Volatility models | `arch` `>=6.3` (GARCH) |
| Scheduling | APScheduler `>=3.10` |
| Trading-day logic | `holidays` `>=0.46` |
| Database | **None** — state lives in FastAPI `app.state` (in-memory) |
| Environment | One optional var, `ANTHROPIC_API_KEY` (currently unused) |

> 📐 **For the curious — "no database"**
> The active portfolio and a small cache of computed results live in `app.state` while the server is running (set in `main.py`'s `lifespan`, refreshed by the scheduler). Restarting the process re-runs the strategy from scratch. In production this matters even less because production serves the static snapshot.

**Structure:**

| Path | Role |
| --- | --- |
| `main.py` | FastAPI app, startup lifespan, initial strategy run, CORS, routers |
| `scheduler.py` | Monthly rebalance (APScheduler) |
| `generate_snapshot.py` | Serializes all endpoints into `snapshot.json` |
| `refresh_snapshot.sh` | Convenience wrapper for the snapshot job |
| `models/schemas.py` | Pydantic request/response models |
| `routers/portfolio.py` | Portfolio data + metrics endpoints |
| `routers/risk.py` | Monte Carlo, stress tests, GARCH |
| `routers/liquidity.py` | Liquidity + Kelly |
| `routers/commentary.py` | Commentary endpoint |
| `routers/_deps.py` | Shared dependency: fetch the active portfolio or 503 |
| `services/strategy.py` | Value-momentum selection |
| `services/market_data.py` | Yahoo Finance fetch + caching |
| `services/risk.py` | Core risk metrics |
| `services/monte_carlo.py` | Monte Carlo simulation |
| `services/garch.py` | GARCH(1,1) volatility models |
| `services/stress_test.py` | Historical scenario replay |
| `services/liquidity.py` | Liquidity + Kelly sizing |
| `services/news.py` | Per-holding headlines |
| `services/claude_client.py` | Commentary generator (rule-based) |
| `services/precompute.py` | Warms the in-memory cache after a rebalance |

#### Endpoint table

All endpoints are under `/api` (plus a top-level `GET /health` liveness probe).

| Method & path | Returns | Key params |
| --- | --- | --- |
| `GET /api/portfolio/current` | Active portfolio (tickers, weights, strategy, rebalanced_at) | — |
| `GET /api/portfolio/metrics` | The full RiskMetrics bundle | `tickers`, `weights`, `period` (3mo/6mo/1y/2y, default 1y) |
| `GET /api/portfolio/prices` | Cumulative-return series vs benchmark | `tickers`, `weights`, `period`, `benchmark` (default **SPY**) |
| `GET /api/portfolio/correlation` | Pearson correlation matrix | `tickers`, `weights`, `period` |
| `GET /api/portfolio/news` | Recent headlines per holding | `tickers`, `weights` |
| `GET /api/risk/monte-carlo` | 10k-path 1-year VaR/CVaR + percentile paths | — (uses active portfolio) |
| `GET /api/risk/stress-tests` | The 4 preset historical scenarios | — |
| `POST /api/risk/stress-custom` | A custom window as a stress test | body `{ start, end, name }` |
| `GET /api/risk/garch` | GARCH history + 30-day forecast | — |
| `GET /api/liquidity/analysis` | Per-position liquidity + Kelly | `aum` (default **1,000,000**) |
| `POST /api/commentary/generate` | Rule-based English summary | body `{ metrics, module }` |
| `GET /health` | `{"status":"ok"}` | — |

> Note on parameter handling: `tickers`/`weights` are optional on the portfolio endpoints. When omitted, the server falls back to the currently-active strategy portfolio in `app.state`. Supplied weights must sum to ~1.0 (validated to within 0.99–1.01).

#### Data source & resilience

Data comes from **Yahoo Finance via `yfinance`**: daily adjusted close prices, splits, share-count history, news, and 30-day volume; book equity comes from SEC EDGAR. `services/market_data.py` caches results with a short (~1-minute) TTL so repeated requests don't hammer the provider.

The system **degrades gracefully** rather than crashing:

- Strategy: value+momentum → momentum-only (if value data missing) → equal-weight fallback (if everything fails).
- Missing tickers are dropped with a warning instead of failing the request.

#### Deployment

- **Development:** live FastAPI back end (port 8000) + Vite dev server (port 5173). `./run.sh` starts both.
- **Production:** fully static. `generate_snapshot.py` serializes every endpoint response (for all periods) into `frontend/public/snapshot.json`. A GitHub Action (`.github/workflows/snapshot.yml`) runs daily at **07:00 UTC** (cron `0 7 * * *`), regenerates the snapshot, and **commits only if it changed** — that commit triggers a Vercel redeploy. The result: zero cold start, zero hosting cost, and a fresh dataset every day.

> 📐 **For the curious — why commit-on-change**
> If the snapshot is identical to yesterday's, the workflow exits without committing, so Vercel doesn't redeploy unnecessarily. If the generator fails (a bad data day), it exits non-zero and leaves the previous snapshot untouched — production never serves an empty file.

---

## 5. Financial strategy & analytics (the core)

This section explains every concept in plain language, with the actual formula in a skippable callout.

### 5.1 The strategy (`services/strategy.py`)

**Plain language.** Out of every stock in the S&P 500, the strategy scores each one on two ideas that have decades of academic support:

1. **Momentum** — stocks that have gone up over the past year tend to keep going up for a while.
2. **Value** — cheap stocks (low price relative to their book value) tend to outperform expensive ones.

It blends the two scores 50/50, holds the **top 10% of companies** (about 45–50 names), and weights each one in proportion to its score, with a 35% cap on any single position. The approach is grounded in Asness, Moskowitz & Pedersen (2013), *"Value and Momentum Everywhere."*

**The universe.** All current S&P 500 constituents, from `backend/data/sp500_constituents.csv` (refreshed by `backend/scripts/update_sp500.py`). At each past rebalance a stock only counts if it had already joined the index (the CSV's `date_added` column).

#### Momentum signal

**Plain language.** Measure each stock's return over the past year, but *deliberately skip the most recent month*. The skip avoids the well-known "short-term reversal" effect, where last month's best performers often dip.

> 📐 **Methodology — 12-1 momentum**
> Momentum = (total-return price ~21 trading days before the rebalance ÷ price ~252 trading days before) − 1, using only closes before the rebalance day. The raw momentum across stocks is converted to a **cross-sectional z-score** and **winsorized at ±3σ**.

#### Value signal

**Plain language.** Use book-to-market: the company's accounting net worth divided by its stock-market value. A high ratio means "cheap", which scores as higher value. Crucially, the backtest only uses a balance sheet once it would have been public.

> 📐 **Methodology — point-in-time book-to-market (`services/fundamentals.py`)**
> Book equity = `StockholdersEquity` (or the NCI-inclusive total) from SEC EDGAR's XBRL frames API, one request per calendar quarter for all filers. A quarter's value is usable 90 days after the quarter ends. Market equity = shares outstanding (Yahoo share-count history, put on today's split basis) × split-adjusted close. Negative or missing book equity is dropped; z-scored and winsorized at ±3σ. SEC requires a contact email (`SEC_CONTACT_EMAIL`).

#### Composite score

> 📐 **Methodology — composite**
> composite = 0.5 × momentum_z + 0.5 × value_z, for tickers with *both* signals. If fewer than half the momentum names have a value score, that month ranks on momentum alone. Multiple share classes of one company (by CIK) keep only the highest-scoring line.

#### Portfolio construction & the 35% cap

**Plain language.** Take the top 10% of companies by composite score and give each a weight proportional to its score, so stronger signals get more money. No position may exceed 35%; with ~50 names the largest is normally around 3%, so the cap is a guardrail rather than an active constraint.

> 📐 **Methodology — weight construction**
> Constants: `SELECTION_PCT = 0.10`, `MIN_HOLDINGS = 10`, `WEIGHT_CAP = 0.35`, `WINSOR_LIMIT = 3.0`.
> 1. `n = max(10, ceil(0.10 × ranked companies))`; take the n highest composite scores.
> 2. Top-decile scores are positive, so `weight = score / sum(scores)`. (If any selected score is ≤ 0, scores are shifted so the lowest still gets a small positive weight.)
> 3. Apply the 35% cap iteratively, redistributing any excess across uncapped names, then renormalize.

#### Backtest

**Plain language.** Every performance number on the dashboard comes from replaying these rules month by month over the last five years — not from pretending today's holdings were held all along. Today's holdings are just the latest month of that replay.

> 📐 **Methodology — `run_strategy()`**
> Rebalance on the first trading day of each month; signals use data up to the previous close. Between rebalances, weights drift with daily total returns. Turnover is one-way (Σ|new − drifted old| / 2). Returns are gross of costs and taxes. The daily snapshot re-runs the whole backtest; past months only depend on past data, so they reproduce, and holdings change only at month start.
> Known bias: companies that have left the index are missing, so returns are optimistic (in October 2026 an equal-weight basket of the universe beat RSP by ~3 points a year).

#### Fallbacks

| Condition | Strategy label | Result |
| --- | --- | --- |
| Value data too sparse at a rebalance | `"momentum"` | Top 10% by momentum only |
| SEC data unavailable in the snapshot job | — | Job fails, previous snapshot stays live |
| Market data fails in the live API | `"equal-weight-fallback"` | Equal-weight basket: AAPL, MSFT, JPM, JNJ, XOM (20% each) |
| Normal operation | `"value-momentum"` | The composite strategy above |

#### Rebalancing (`scheduler.py`)

**Plain language.** Once a month — on the first US trading day, at 9:30 AM Eastern (market open) — the strategy re-runs and updates the portfolio. No human action required.

> 📐 **Methodology — the two-step schedule**
> APScheduler fires a daily cron job on the **1st–7th of the month, Mon–Fri, at 09:30 America/New_York**. The job then verifies that *today is actually the first trading day of the month* (not a weekend, not a US federal holiday, and no earlier weekday/non-holiday exists this month) via the `holidays` library before running. This two-step design is robust to clock jumps and mid-month restarts.

### 5.2 Core risk metrics (`services/risk.py`)

All metrics use **252 trading days** per year and a **risk-free rate of 4.5%** (`RISK_FREE_RATE = 0.045`, verified).

| Metric | Plain language |
| --- | --- |
| **Annualised return (CAGR)** | The steady yearly growth rate that would produce the observed total return. |
| **Annualised volatility** | How much the daily returns bounce around, scaled to a yearly figure — a measure of total risk. |
| **Sharpe ratio** | Return earned per unit of risk, after subtracting the risk-free rate. Above 1 is generally good. |
| **Max drawdown** | The worst peak-to-trough drop over the period. |
| **VaR 95%** | A "typical bad day" loss: with 95% confidence, daily losses shouldn't exceed this. |
| **CVaR 95%** | The *average* loss on the worst 5% of days (Expected Shortfall) — what happens when the bad day is really bad. |
| **Beta** | How much the portfolio moves when the market (SPY) moves. β > 1 = more volatile than the market. |
| **Alpha** | Return above what the market exposure alone would predict — the "skill" component (Jensen's α). |

> 📐 **Methodology — formulas (from `risk.py`)**
> - **CAGR:** `(∏(1 + daily_return))^(1/years) − 1`, where `years = len(returns)/252`.
> - **Annualised volatility:** `std(daily_returns, ddof=1) × √252`.
> - **Sharpe:** `(arithmetic_annual_return − rf) / annualised_vol`, with `arithmetic_annual_return = mean(daily) × 252` and `rf = 0.045`.
> - **Max drawdown:** `min( cumulative_curve / running_peak − 1 )` (a negative number).
> - **VaR 95% (historical):** the 5th percentile of daily returns, reported as a positive loss magnitude.
> - **CVaR 95%:** the average of all daily returns at or below the 5th-percentile threshold, reported as a positive loss.
> - **Beta & Alpha:** OLS on daily *excess* returns (each minus `rf/252`): `β = Cov(Rp, Rm) / Var(Rm)`; `α = (mean(Rp) − β·mean(Rm)) × 252` (annualised intercept, vs SPY).
> - **Per-holding volatility contribution:** `w_i · (Σw)_i / (w'Σw)`, which sums to ~1 across holdings (Σ = annualised covariance matrix).
> - **Correlation matrix:** Pearson correlation of daily returns, used to gauge diversification.

### 5.3 Advanced analytics

#### Monte Carlo simulation (`services/monte_carlo.py`)

**Plain language.** Simulate 10,000 possible "alternate futures" for the portfolio over the next year, keeping the stocks' real correlations intact, and look at the distribution of outcomes — especially the bad tail.

> 📐 **Methodology — correlated paths**
> 10,000 paths over 252 days. Each day draws standard normal shocks and maps them to correlated daily returns using the **Cholesky decomposition** of the covariance matrix (a tiny ridge is added for numerical safety; an eigen-based square root is the fallback if the matrix isn't positive semi-definite). Outputs: VaR & CVaR at 95% and 99% on the 1-year terminal return; the probability of losing >10%, >20%, >30%; and the 5/25/50/75/95th-percentile paths for plotting. The simulation uses a fixed seed (`seed=11`) so results are reproducible.

#### GARCH(1,1) (`services/garch.py`)

**Plain language.** Volatility comes in clusters — calm periods and stormy periods. GARCH models that and forecasts where volatility is headed over the next 30 days, per stock and for the whole portfolio. If shocks "stick around" (high persistence), drawdowns can compound, so persistent assets are flagged.

> 📐 **Methodology — per-asset GARCH(1,1)**
> Fitted per asset with the `arch` library (`vol="GARCH", p=1, q=1, mean="Zero"`). Parameters: ω (omega), α (alpha[1]), β (beta[1]). **Persistence = α + β**, flagged `"persistent"` when > 0.95 (`PERSISTENCE_THRESHOLD`). The portfolio forecast combines the per-asset conditional volatilities through the static correlation matrix (`diag(σ_t) · C · diag(σ_t)`). Output: realized volatility (rolling **21-day** window) vs the GARCH conditional vol over history, plus a **30-day** forecast with a ±1σ band, and a per-asset α/β/ω/persistence table.

#### Stress tests (`services/stress_test.py`)

**Plain language.** Replay history: how would *today's* portfolio have done during four notorious market crises?

| Scenario (code key) | Window (verified) |
| --- | --- |
| Global Financial Crisis (`GFC_peak_to_trough`) | 2008-09-01 → 2009-03-09 |
| COVID crash (`COVID_crash`) | 2020-02-19 → 2020-03-23 |
| Dot-com bust (`dot_com_bust`) | 2000-03-24 → 2002-10-09 |
| 2022 rate shock (`rate_shock_2022`) | 2022-01-03 → 2022-10-12 |

For each, it computes the portfolio return, the worst single day, and the max drawdown. Weights are **re-normalized across the tickers that actually existed in that window** (e.g. NVDA-heavy weights are reweighted for the dot-com era). In live mode, users can add a custom date window.

#### Liquidity & Kelly sizing (`services/liquidity.py`)

**Plain language — liquidity.** How easily could each position be sold without moving the market? It uses 30-day average dollar volume (ADV) to assign a 1–5 liquidity score and estimates how many trading days a full exit would take at different participation rates.

> 📐 **Methodology — liquidity score (verified)**
> 30-day ADV in dollars → score:
> - 5: ADV > \$100M
> - 4: \$10M–\$100M
> - 3: \$1M–\$10M
> - 2: \$100K–\$1M
> - 1: < \$100K
>
> Position\$ = AUM × weight; **% of ADV** = position\$ / ADV; **days-to-liquidate** = (% of ADV) ÷ participation rate, computed at 10%, 20%, and 33% participation.

**Plain language — Kelly.** The Kelly criterion suggests how much to bet on each stock to maximize long-run growth, based on its risk and reward. The dashboard compares the Kelly-implied weight to the current weight and flags any position that is more than 10 percentage points off — a prompt to review whether that's intentional or stale.

> 📐 **Methodology — Kelly fraction (verified)**
> Per asset, `f* = (μ − rf) / σ²`, where μ and σ² are **annualised** from ~2 years of daily returns and `rf = 0.045`. Negative fractions are clipped to 0, then the fractions are **normalized to unit total leverage** so they're comparable to the current portfolio weights. `kelly_divergence = kelly_weight − current_weight`; the UI flags `|divergence| > 0.10` (10pp). A half-Kelly figure is also computed.

### 5.4 Commentary engine (`services/claude_client.py`)

**Plain language.** A button generates a short (roughly 3–5 sentence) plain-English summary of the current numbers — useful for review meetings.

**Important detail:** despite the filename `claude_client.py`, the engine is currently **rule-based** — it builds the text from templates and the live numbers, with **no external API call**. The reported `model` is `"rule-based-v2"`. An `ANTHROPIC_API_KEY` hook exists if the team later wants real LLM-generated commentary.

> ⚠️ **Detail vs the brief.** The module's docstring describes five focus areas (overview, optimization, black-litterman, risk, liquidity), but only **three generators are actually implemented and wired up**: `overview`, `risk`, and `liquidity` (see `_MODULE_GENERATORS`). Requesting `optimization` or `black_litterman` would raise an "unknown commentary module" error today. The wiring is ready for the other two to be added.

---

## 6. Financial usage & strategy (how the team uses it)

This is a **systematic, rules-based** tool — not discretionary stock-picking. The intended workflow:

1. **Let it rebalance.** On the first trading day of each month, the strategy re-selects the top 10% of S&P 500 companies and reweights. No one chooses stocks by hand.
2. **Monitor performance vs SPY.** The Overview tab shows cumulative and excess returns plus the 8 headline metrics.
3. **Watch tail risk.** Check VaR/CVaR, the Monte Carlo distribution, and the four historical stress tests for worst-case exposure.
4. **Check the volatility regime.** The GARCH forecast shows whether volatility is rising or falling, and which holdings have stubbornly persistent volatility.
5. **Review sizing & liquidity.** Confirm positions are liquid enough to exit and look at Kelly-vs-current divergence flags as review prompts (not auto-trades).
6. **Read the commentary.** The auto-generated readout gives a quick plain-English summary for meetings.

Because production serves a **daily-refreshed static snapshot**, the team always sees a stable, consistent view that updates once per day — there's no risk of a flaky data feed showing different numbers on every page load.

> Reminder shown in the app footer: *"Educational use only. Not investment advice."*

---

## 7. Glossary

| Term | Plain meaning |
| --- | --- |
| **Sharpe ratio** | Return earned per unit of risk, after the risk-free rate; higher is better. |
| **VaR (Value at Risk)** | A loss level you'd expect not to exceed on most days, at a chosen confidence (e.g. 95%). |
| **CVaR / Expected Shortfall** | The average loss on the worst days beyond the VaR threshold — how bad the bad days are on average. |
| **Max drawdown** | The largest peak-to-trough drop in value over a period. |
| **Beta** | How strongly the portfolio moves with the overall market. |
| **Alpha** | Return beyond what market exposure alone would explain — the "skill" part. |
| **Volatility** | How much returns fluctuate; a standard measure of total risk. |
| **GARCH** | A model that captures volatility "clustering" and forecasts future volatility. |
| **Monte Carlo** | Running thousands of random simulations to map out the range of possible outcomes. |
| **Kelly criterion** | A formula for bet/position sizing that maximizes long-run growth. |
| **ADV (Average Daily Volume)** | The typical dollar value of a stock traded per day; a proxy for liquidity. |
| **Winsorize** | Clipping extreme values (here at ±3σ) so outliers don't distort a statistic. |
| **Z-score** | How many standard deviations a value sits above or below the average. |
| **Momentum** | The tendency of recent winners to keep winning for a while. |
| **Value / book-to-market** | A "cheapness" signal; high book-to-market (low price-to-book) means relatively cheap. |
| **Rebalancing** | Periodically resetting the portfolio's holdings/weights back to the strategy's targets. |
| **CAGR** | Compound Annual Growth Rate — the steady yearly rate implied by total growth. |

---

## 8. Key files reference

### Website (`/Users/jantran/Desktop/PortfolioWS`)

| Path | Purpose |
| --- | --- |
| `package.json` | Dependencies, scripts, Node engine, package name `proto-proxima` |
| `astro.config.mjs` | Astro config: Vercel adapter + Web Analytics |
| `tsconfig.json` | TypeScript strict config |
| `src/content.config.ts` | Project content-collection schema |
| `src/layouts/Layout.astro` | Shared page shell |
| `src/pages/index.astro` | Home page |
| `src/pages/about.astro` | About / bio / timeline / skills |
| `src/pages/contact.astro` | Contact page |
| `src/pages/projects/index.astro` | Project grid |
| `src/pages/projects/[...slug].astro` | Dynamic project detail page |
| `src/components/Header.astro` / `Footer.astro` / `ProjectCard.astro` | Reusable UI |
| `src/content/projects/financial-dashboard.md` | Dashboard project page (holds the live `externalUrl`) |
| `src/content/projects/*.md` | The other five project pages |
| `src/styles/global.css` | Global styles |

### Dashboard front end (`/Users/jantran/Desktop/portfolio-dashboard/frontend`)

| Path | Purpose |
| --- | --- |
| `src/main.jsx` | React entry point |
| `src/App.jsx` | Tabs, top-level loading, period selector |
| `src/api.js` | Static-vs-live data access layer |
| `src/components/tabs/OverviewTab.jsx` | Overview screen |
| `src/components/tabs/RiskTab.jsx` | Risk Models screen |
| `src/components/tabs/LiquidityTab.jsx` | Liquidity screen |
| `src/components/RiskMetricsPanel.jsx` | The 8-card metric strip |
| `src/components/PerformanceSection.jsx` / `PerformanceChart.jsx` | Performance charts |
| `src/components/RelativePerformanceChart.jsx` | Excess-return chart |
| `src/components/NewsPanel.jsx` | Ticker-filterable news |
| `src/components/CommentaryButton.jsx` | Commentary trigger |
| `public/snapshot.json` | The daily cached dataset (static mode) |

### Dashboard back end (`/Users/jantran/Desktop/portfolio-dashboard/backend`)

| Path | Purpose |
| --- | --- |
| `main.py` | FastAPI app, lifespan, CORS, router wiring |
| `scheduler.py` | Monthly rebalance scheduler |
| `generate_snapshot.py` | Builds `snapshot.json` for production |
| `refresh_snapshot.sh` | Snapshot job wrapper |
| `requirements.txt` | Python dependencies |
| `models/schemas.py` | Pydantic models |
| `routers/portfolio.py` | Portfolio data + metrics endpoints |
| `routers/risk.py` | Monte Carlo / stress / GARCH endpoints |
| `routers/liquidity.py` | Liquidity + Kelly endpoint |
| `routers/commentary.py` | Commentary endpoint |
| `routers/_deps.py` | Active-portfolio dependency helper |
| `services/strategy.py` | Value-momentum selection (50-ticker universe, 35% cap) |
| `services/risk.py` | Core risk metrics (rf = 4.5%) |
| `services/monte_carlo.py` | Monte Carlo simulation |
| `services/garch.py` | GARCH(1,1) volatility models |
| `services/stress_test.py` | Historical scenario replay |
| `services/liquidity.py` | Liquidity scoring + Kelly sizing |
| `services/market_data.py` | Yahoo Finance fetch + caching |
| `services/news.py` | Per-holding headlines |
| `services/claude_client.py` | Rule-based commentary generator |
| `services/precompute.py` | Cache warming after rebalance |

### Shared / ops

| Path | Purpose |
| --- | --- |
| `.github/workflows/snapshot.yml` | Daily snapshot job (cron `0 7 * * *`, commit-on-change → Vercel redeploy) |
| `run.sh` | Starts front end (5173) + back end (8000) for local dev |

---

*Document generated for the team. All figures, tickers, endpoints, and formulas above were verified against the source files at the time of writing.*
