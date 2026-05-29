"""Liquidity + Kelly sizing endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Query, Request

from models.schemas import LiquidityPosition, LiquidityResponse
from routers._deps import active_portfolio
from services import liquidity as liq_service

router = APIRouter(prefix="/api/liquidity", tags=["liquidity"])


@router.get("/analysis", response_model=LiquidityResponse)
async def analysis(
    request: Request,
    aum: float = Query(1_000_000.0, gt=0),
) -> LiquidityResponse:
    """Per-position liquidity profile + Kelly sizing for the active book."""
    # Serve from precomputed cache when AUM matches the default (1M).
    # Custom AUM values always recompute so the position sizes are correct.
    cache = getattr(request.app.state, "cache", {})
    if aum == 1_000_000.0 and (cached := cache.get("liquidity")):
        return LiquidityResponse(
            aum=cached["aum"],
            positions=[LiquidityPosition(**p) for p in cached["positions"]],
        )

    active = active_portfolio(request)
    result = await liq_service.liquidity_analysis(
        list(active["tickers"]), list(active["weights"]), aum=aum
    )
    return LiquidityResponse(
        aum=result["aum"],
        positions=[LiquidityPosition(**p) for p in result["positions"]],
    )
