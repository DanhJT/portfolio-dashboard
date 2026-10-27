# Portfolio Risk Dashboard

A local equity portfolio risk dashboard with a FastAPI backend, a React +
Recharts frontend, and an automated senior-analyst commentary panel.

No API keys, no paid services — yfinance for market data and a local
rule-based commentary generator for the AI panel.

## Stack

- **Backend:** Python 3.11+, FastAPI, Pydantic v2, yfinance, pandas, numpy
- **Frontend:** React 18, Vite, Tailwind CSS, Recharts
- **Commentary:** rule-based Python module that interprets the risk
  metrics and emits a 3–5 sentence readout

## Layout

```
portfolio-dashboard/
├── backend/
│   ├── main.py               # FastAPI app entrypoint
│   ├── routers/              # portfolio.py, commentary.py
│   ├── services/             # market_data.py, risk.py, claude_client.py
│   └── models/schemas.py
├── frontend/
│   ├── src/components/       # PortfolioTable, RiskMetricsPanel, PerformanceChart, AICommentary
│   ├── src/App.jsx
│   └── package.json
└── run.sh
```

`services/claude_client.py` is kept under that filename for historical
reasons — it now generates commentary locally without calling any external
API. The route shape and frontend integration are unchanged.

## Setup

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Frontend

```bash
cd frontend
npm install
```

## Running

### One command (both servers)

```bash
./run.sh
```

This starts the backend on `http://localhost:8000` and the frontend on
`http://localhost:5173`. `Ctrl+C` stops both.

### Manually

```bash
# Terminal 1
cd backend
source .venv/bin/activate
uvicorn main:app --reload --port 8000

# Terminal 2
cd frontend
npm run dev
```

Open <http://localhost:5173>.

## API

| Method | Path                          | Description                                              |
|-------:|-------------------------------|----------------------------------------------------------|
| GET    | `/api/portfolio/metrics`      | Full risk metrics for the portfolio                      |
| GET    | `/api/portfolio/prices`       | Cumulative return series vs SPY                          |
| GET    | `/api/portfolio/correlation`  | Correlation matrix between holdings                      |
| POST   | `/api/commentary/generate`    | Senior-analyst commentary on a metrics payload           |
| GET    | `/health`                     | Liveness probe                                           |

All `/api/portfolio/*` endpoints accept optional query params:

```
?tickers=AAPL&tickers=MSFT&weights=0.5&weights=0.5&period=1y
```

`period` is one of `3mo`, `6mo`, `1y`, `2y`. If omitted, the default
portfolio is used: 25% AAPL, 25% MSFT, 20% NVDA, 15% JPM, 15% BRK-B.

## Strategy universe

The strategy ranks **all current S&P 500 constituents**, read from
[backend/data/sp500_constituents.csv](backend/data/sp500_constituents.csv)
(symbol, name, GICS sector, CIK, date added). Nothing scrapes Wikipedia at
runtime, so the universe is reproducible from the repo alone.

Refresh the list after S&P's quarterly index changes:

```bash
backend/.venv/bin/python backend/scripts/update_sp500.py
```

That rewrites the CSV and `frontend/src/sp500Sectors.json` (the ticker → GICS
sector map for the frontend). Commit both. Symbols use Yahoo's
convention (`BRK-B`, not `BRK.B`), and the CIK column lets the strategy collapse
multiple share classes of one issuer (GOOGL/GOOG) into a single position.

The backtest only ranks a stock from the date it joined the index, so later
additions can't leak backwards. Companies that have since left the index are
missing, which leaves some survivorship bias (see the About tab).

## Strategy and backtest

Each month the strategy holds the **top 10%** of S&P 500 companies by a 50/50
blend of 12-1 momentum and book-to-market z-scores, weighted in proportion to
score and capped at 35% per name. `services/strategy.py` runs these rules on the
first trading day of every month over the last five years, using only data from
before each date; the live holdings are the latest of those rebalances, and every
performance figure on the dashboard comes from the backtest.

Book equity comes from SEC EDGAR's XBRL frames API (used 90 days after each
quarter ends) and shares outstanding from Yahoo's share-count history; see
`services/fundamentals.py`. SEC needs a contact email, so set
`SEC_CONTACT_EMAIL` in the repo-root `.env` locally and as a repository secret
for the GitHub Action. Downloads are cached in `backend/.cache`.

## Risk metric definitions

- **Annualised return** — CAGR implied by the daily portfolio return series.
- **Annualised volatility** — std-dev of daily returns × √252.
- **Sharpe ratio** — `(mean × 252 − rf) / annualised_vol`, with `rf = 4.5%`.
- **Max drawdown** — worst peak-to-trough on the cumulative return curve.
- **VaR 95%** — historical 5th percentile of daily losses (positive number).
- **CVaR 95%** — average loss conditional on breaching the VaR threshold.
- **Volatility contribution** — `w_i · (Σw)_i / (w'Σw)`; sums to ~1.0.

## Commentary logic

The commentary engine ([backend/services/claude_client.py](backend/services/claude_client.py))
classifies each metric into a band and stitches together four sentences:

1. **Risk profile** — Sharpe band × volatility band.
2. **Concentration** — largest weight + largest vol contribution.
3. **VaR/CVaR** — translated into plain-language daily loss expectations.
4. **Action** — prioritised recommendation based on which risk dominates.

Swapping in a real LLM is a one-function change: replace
`generate_commentary` with an API call and keep the same return signature.

## Deployment (static snapshot)

The production site is **fully static** — no live backend. yfinance is
rate-limited/blocked from datacenter IPs, so instead of fetching live on every
request, a generator produces a daily `frontend/public/snapshot.json` that the
frontend reads directly from the CDN. The result: instant load, zero cold
start, $0 hosting, and it can never crash from a bad data day.

### How it works

```
generate_snapshot.py  ──►  frontend/public/snapshot.json  ──►  Vercel (static)
   (runs strategy +              (committed to git;              served from CDN
    all analytics,                triggers Vercel deploy)         by api.js)
    reuses live services)
```

- **Data source toggle** — `frontend/src/api.js` reads `VITE_DATA_SOURCE`:
  - `static` (default, used in production) — reads `snapshot.json`.
  - `live` — hits the FastAPI backend; set `VITE_DATA_SOURCE=live` for local
    development against `uvicorn`.
- The backend is retained for **local development** and as the
  **snapshot-generation engine** — it is no longer needed in production.
- In static mode the custom stress-window input is hidden (it needs live
  compute); the four preset historical scenarios remain. Liquidity AUM is
  recomputed client-side.

### Refreshing the snapshot

**Automatic (daily):** `.github/workflows/snapshot.yml` runs every day at
07:00 UTC (and on-demand via the Actions tab), regenerates the snapshot, and
commits it only if it changed — which triggers a Vercel redeploy. On any data
failure it leaves the existing snapshot untouched.

**Manual / fallback:** if GitHub's runners get rate-limited by Yahoo, refresh
from your own machine (residential IPs are rarely blocked):

```bash
./backend/refresh_snapshot.sh
```

This regenerates the snapshot and pushes it.

### Regenerate locally without pushing

```bash
cd backend && python generate_snapshot.py   # writes ../frontend/public/snapshot.json
```

### Env vars

| Var                 | Effect                                                                 |
|---------------------|------------------------------------------------------------------------|
| `SEC_CONTACT_EMAIL` | Contact email SEC EDGAR requires for book-equity data. Without it the snapshot run fails rather than publishing momentum-only holdings. |
| `ALLOW_MOMENTUM_ONLY=1` | Publish anyway when value data is unavailable. |
| `SCREEN_ON_STARTUP=1` | `main.py` runs the full screen at startup instead of seeding holdings from `snapshot.json`. |

Every daily run re-runs the backtest. Past rebalances only use data from before
their date, so they come out the same each day, and the holdings only change on
the first US trading day of the month.

## Notes

- Educational use only — not investment advice.
- `yfinance` data is delayed and best-effort. Tickers with no data are
  dropped with a log warning rather than failing the request.
- If value data is too thin at a rebalance, that month ranks on momentum
  alone. The live API falls back to an equal-weight basket if market data can't
  be loaded at all; the snapshot generator instead exits and keeps the
  previous snapshot.
