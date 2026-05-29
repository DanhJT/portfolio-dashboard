"""FastAPI application entrypoint."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import (
    commentary,
    liquidity,
    portfolio,
    risk,
)
from scheduler import start_scheduler
from services.strategy import run_value_momentum_strategy

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run the strategy once at startup and arm the monthly rebalance scheduler."""
    logger.info("running value-momentum strategy at startup…")
    portfolio = await asyncio.to_thread(run_value_momentum_strategy)
    app.state.portfolio = portfolio
    logger.info(
        "initial portfolio: %s | weights: %s",
        portfolio["tickers"],
        [round(w, 4) for w in portfolio["weights"]],
    )
    scheduler = start_scheduler(app)
    app.state.scheduler = scheduler
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="Portfolio Risk Dashboard API",
    version="0.2.0",
    description="Live value-momentum equity portfolio + risk dashboard.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://portfolio-dashboard-five-iota.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(portfolio.router)
app.include_router(commentary.router)
app.include_router(risk.router)
app.include_router(liquidity.router)


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}
