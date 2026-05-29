"""Portfolio data + metrics endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from models.schemas import (
    ActivePortfolio,
    CorrelationResponse,
    HoldingMetrics,
    NewsItem,
    NewsResponse,
    PricePoint,
    PriceSeriesResponse,
    RiskMetrics,
)
from services import market_data, news, risk

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


def _parse_portfolio(
    request: Request,
    tickers: list[str] | None,
    weights: list[float] | None,
) -> tuple[list[str], dict[str, float]]:
    """Resolve query params -> (tickers, weights_map). Falls back to app.state.portfolio."""
    active = getattr(request.app.state, "portfolio", None)
    if not tickers:
        tickers = (active or {}).get("tickers", [])
    if not weights:
        weights = (active or {}).get("weights", [])
    if not tickers or not weights:
        raise HTTPException(503, "active portfolio not initialised yet")
    if len(tickers) != len(weights):
        raise HTTPException(400, "tickers and weights length mismatch")
    total = sum(weights)
    if not 0.99 <= total <= 1.01:
        raise HTTPException(400, f"weights must sum to 1.0 (got {total:.4f})")
    return tickers, dict(zip(tickers, weights))


@router.get("/current", response_model=ActivePortfolio)
async def get_current(request: Request) -> ActivePortfolio:
    """Return the currently-active strategy portfolio."""
    active = getattr(request.app.state, "portfolio", None)
    if not active:
        raise HTTPException(503, "active portfolio not initialised yet")
    return ActivePortfolio(**active)


@router.get("/metrics", response_model=RiskMetrics)
async def get_metrics(
    request: Request,
    tickers: list[str] | None = Query(default=None),
    weights: list[float] | None = Query(default=None),
    period: str = Query("1y"),
) -> RiskMetrics:
    """Run the risk suite on the (default or supplied) portfolio."""
    tickers, weight_map = _parse_portfolio(request, tickers, weights)
    try:
        prices, bench = await market_data.fetch_with_benchmark(tickers, period=period)
    except ValueError as exc:
        raise HTTPException(502, str(exc)) from exc
    bench = bench if not bench.empty else None
    metrics = risk.compute_portfolio_metrics(prices, weight_map, benchmark=bench)
    return RiskMetrics(
        annualised_return=metrics.annualised_return,
        annualised_volatility=metrics.annualised_volatility,
        sharpe_ratio=metrics.sharpe_ratio,
        max_drawdown=metrics.max_drawdown,
        var_95=metrics.var_95,
        cvar_95=metrics.cvar_95,
        alpha=metrics.alpha,
        beta=metrics.beta,
        holdings=[
            HoldingMetrics(
                ticker=h.ticker,
                weight=h.weight,
                annualised_return=h.annualised_return,
                annualised_volatility=h.annualised_volatility,
                volatility_contribution=h.volatility_contribution,
            )
            for h in metrics.holdings
        ],
        start_date=metrics.start_date.date(),
        end_date=metrics.end_date.date(),
    )


@router.get("/prices", response_model=PriceSeriesResponse)
async def get_prices(
    request: Request,
    tickers: list[str] | None = Query(default=None),
    weights: list[float] | None = Query(default=None),
    period: str = Query("1y"),
    benchmark: str = Query("SPY"),
) -> PriceSeriesResponse:
    """Cumulative-return series for the portfolio and benchmark."""
    tickers, weight_map = _parse_portfolio(request, tickers, weights)
    try:
        prices, bench = await market_data.fetch_with_benchmark(
            tickers, period=period, benchmark=benchmark
        )
    except ValueError as exc:
        raise HTTPException(502, str(exc)) from exc

    port_returns = risk.portfolio_returns(prices, weight_map)
    port_curve = risk.cumulative_curve(port_returns)
    bench_curve = risk.cumulative_curve(bench.pct_change().dropna())

    common = port_curve.index.intersection(bench_curve.index)
    series = [
        PricePoint(
            date=ts.date(),
            portfolio=float(port_curve.loc[ts]),
            benchmark=float(bench_curve.loc[ts]),
        )
        for ts in common
    ]
    return PriceSeriesResponse(series=series, benchmark_ticker=benchmark)


@router.get("/correlation", response_model=CorrelationResponse)
async def get_correlation(
    request: Request,
    tickers: list[str] | None = Query(default=None),
    weights: list[float] | None = Query(default=None),
    period: str = Query("1y"),
) -> CorrelationResponse:
    """Return the pairwise correlation matrix of daily returns."""
    tickers, _ = _parse_portfolio(request, tickers, weights)
    try:
        prices = await market_data.fetch_prices(tickers, period=period)
    except ValueError as exc:
        raise HTTPException(502, str(exc)) from exc

    corr = risk.correlation_matrix(prices)
    return CorrelationResponse(
        tickers=list(corr.columns),
        matrix=[[float(v) for v in row] for row in corr.values],
    )


@router.get("/news", response_model=NewsResponse)
async def get_news(
    request: Request,
    tickers: list[str] | None = Query(default=None),
    weights: list[float] | None = Query(default=None),
) -> NewsResponse:
    """Recent news headlines for each holding, newest first."""
    tickers, _ = _parse_portfolio(request, tickers, weights)
    raw = await news.fetch_news(tickers)
    return NewsResponse(items=[NewsItem(**item) for item in raw])
