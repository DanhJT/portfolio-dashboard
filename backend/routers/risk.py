"""Advanced risk endpoints: Monte Carlo VaR, stress tests, GARCH."""
from __future__ import annotations

import asyncio

import numpy as np
from fastapi import APIRouter, HTTPException, Request

from models.schemas import (
    CustomStressRequest,
    GarchAssetParams,
    GarchResponse,
    MonteCarloResponse,
    StressScenario,
    StressTestResponse,
)
from routers._deps import active_portfolio
from services import garch, market_data, monte_carlo, stress_test

router = APIRouter(prefix="/api/risk", tags=["risk"])

LOOKBACK = "2y"


@router.get("/monte-carlo", response_model=MonteCarloResponse)
async def monte_carlo_endpoint(request: Request) -> MonteCarloResponse:
    """Run 10k-path Monte Carlo VaR over a 1-year horizon."""
    active = active_portfolio(request)
    tickers = list(active["tickers"])
    weights = list(active["weights"])
    try:
        prices = await market_data.fetch_prices(tickers, period=LOOKBACK)
    except ValueError as exc:
        raise HTTPException(502, str(exc)) from exc
    returns = prices.pct_change().dropna(how="all")
    cols = list(returns.columns)
    weight_map = dict(zip(tickers, weights))
    w_aligned = np.array([weight_map.get(c, 0.0) for c in cols], dtype=float)
    s = w_aligned.sum()
    if s > 0:
        w_aligned = w_aligned / s
    result = await asyncio.to_thread(
        monte_carlo.simulate_portfolio_paths, returns, w_aligned
    )
    return MonteCarloResponse(**result)


@router.get("/stress-tests", response_model=StressTestResponse)
async def stress_tests_endpoint(request: Request) -> StressTestResponse:
    """Replay each preset historical scenario."""
    active = active_portfolio(request)
    rows = await asyncio.to_thread(
        stress_test.run_all_scenarios, list(active["tickers"]), list(active["weights"])
    )
    return StressTestResponse(
        scenarios=[StressScenario(**r) for r in rows]
    )


@router.post("/stress-custom", response_model=StressScenario)
async def stress_custom(
    request: Request, payload: CustomStressRequest
) -> StressScenario:
    """Run a user-specified date window as a stress scenario."""
    active = active_portfolio(request)
    row = await asyncio.to_thread(
        stress_test.run_scenario,
        payload.name,
        list(active["tickers"]),
        list(active["weights"]),
        payload.start,
        payload.end,
    )
    return StressScenario(**row)


@router.get("/garch", response_model=GarchResponse)
async def garch_endpoint(request: Request) -> GarchResponse:
    """Fit GARCH(1,1) per asset and return historical + 30-day-ahead vol."""
    active = active_portfolio(request)
    tickers = list(active["tickers"])
    weights = list(active["weights"])
    try:
        prices = await market_data.fetch_prices(tickers, period=LOOKBACK)
    except ValueError as exc:
        raise HTTPException(502, str(exc)) from exc
    returns = prices.pct_change().dropna(how="all")
    cols = list(returns.columns)
    weight_map = dict(zip(tickers, weights))
    w_aligned = np.array([weight_map.get(c, 0.0) for c in cols], dtype=float)
    s = w_aligned.sum()
    if s > 0:
        w_aligned = w_aligned / s
    result = await asyncio.to_thread(
        garch.portfolio_garch_vol_forecast, returns, w_aligned
    )
    return GarchResponse(
        historical_vol=result["historical_vol"],
        forecast_vol=result["forecast_vol"],
        forecast_band_low=result["forecast_band_low"],
        forecast_band_high=result["forecast_band_high"],
        history=result["history"],
        forward=result["forward"],
        assets=[GarchAssetParams(**a) for a in result["assets"]],
        persistent_assets=result["persistent_assets"],
    )
