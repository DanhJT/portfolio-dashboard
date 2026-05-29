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

## Notes

- Educational use only — not investment advice.
- `yfinance` data is delayed and best-effort. Tickers with no data are
  dropped with a log warning rather than failing the request.
