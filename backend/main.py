"""FastAPI application entrypoint."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import (
    commentary,
    liquidity,
    portfolio,
    risk,
)
from scheduler import start_scheduler
from services import precompute
from services.strategy import run_value_momentum_strategy

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "frontend" / "public" / "snapshot.json"


def _portfolio_from_snapshot() -> dict | None:
    """The holdings recorded in the committed snapshot, if it has any.

    Screening the full S&P 500 takes minutes, and holdings only change on the
    monthly rebalance, so local startup (and every `--reload` restart) reuses
    the snapshot's portfolio instead of re-running the screen.
    """
    try:
        blob = json.loads(SNAPSHOT_PATH.read_text())
    except (OSError, ValueError) as exc:
        logger.info("no usable snapshot to seed from (%s)", exc)
        return None
    portfolio = blob.get("portfolio") or {}
    if portfolio.get("tickers") and portfolio.get("weights"):
        return portfolio
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Seed the portfolio at startup and arm the monthly rebalance scheduler."""
    portfolio = None if os.environ.get("SCREEN_ON_STARTUP") == "1" else _portfolio_from_snapshot()
    if portfolio:
        logger.info(
            "seeded portfolio from snapshot.json (rebalanced_at %s) — "
            "set SCREEN_ON_STARTUP=1 to re-run the screen instead",
            portfolio.get("rebalanced_at"),
        )
    else:
        logger.info("running value-momentum strategy at startup…")
        portfolio = await asyncio.to_thread(run_value_momentum_strategy)
    app.state.portfolio = portfolio
    app.state.cache = {}
    logger.info(
        "initial portfolio: %s | weights: %s",
        portfolio["tickers"],
        [round(w, 4) for w in portfolio["weights"]],
    )
    # Hold a strong reference so the task isn't GC'd mid-flight.
    app.state.precompute_task = asyncio.create_task(precompute.precompute_all(app))
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
