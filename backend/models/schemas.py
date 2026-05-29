"""Pydantic v2 request/response schemas for the portfolio dashboard API."""
from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Holding(BaseModel):
    """A single portfolio holding."""

    ticker: str = Field(..., description="Ticker symbol, e.g. AAPL")
    weight: float = Field(..., ge=0.0, le=1.0, description="Portfolio weight in [0, 1]")


class PortfolioRequest(BaseModel):
    """Portfolio definition supplied via query / body."""

    holdings: list[Holding]
    period: str = Field("1y", description="Lookback period: 3mo, 6mo, 1y, 2y")

    @field_validator("holdings")
    @classmethod
    def _weights_sum_to_one(cls, v: list[Holding]) -> list[Holding]:
        total = sum(h.weight for h in v)
        if not 0.99 <= total <= 1.01:
            raise ValueError(f"weights must sum to 1.0 (got {total:.4f})")
        return v


class HoldingMetrics(BaseModel):
    """Per-holding diagnostics."""

    ticker: str
    weight: float
    annualised_return: float
    annualised_volatility: float
    volatility_contribution: float


class RiskMetrics(BaseModel):
    """Portfolio-level risk metrics."""

    annualised_return: float
    annualised_volatility: float
    sharpe_ratio: float
    max_drawdown: float
    var_95: float
    cvar_95: float
    alpha: float
    beta: float
    holdings: list[HoldingMetrics]
    start_date: date
    end_date: date


class PricePoint(BaseModel):
    """One point in a return / price series."""

    date: date
    portfolio: float
    benchmark: float | None = None


class PriceSeriesResponse(BaseModel):
    """Cumulative-return series for portfolio and benchmark."""

    series: list[PricePoint]
    benchmark_ticker: str = "SPY"


class CorrelationResponse(BaseModel):
    """Correlation matrix between holdings."""

    tickers: list[str]
    matrix: list[list[float]]


class ActivePortfolio(BaseModel):
    """The currently-active strategy portfolio held in app.state."""

    tickers: list[str]
    weights: list[float]
    strategy: str
    rebalanced_at: str | None = None


class NewsItem(BaseModel):
    """One news story related to a portfolio holding."""

    ticker: str
    title: str
    publisher: str | None = None
    url: str | None = None
    published_at: str | None = None
    summary: str | None = None


class NewsResponse(BaseModel):
    """Bundle of recent news across the portfolio's holdings."""

    items: list[NewsItem]


class MonteCarloResponse(BaseModel):
    var_95: float
    var_99: float
    cvar_95: float
    cvar_99: float
    p_loss_10: float
    p_loss_20: float
    p_loss_30: float
    percentile_paths: dict[str, list[float]]
    horizon_days: int
    n_simulations: int


class StressScenario(BaseModel):
    name: str
    start: str
    end: str
    portfolio_return: float | None
    worst_day: float | None
    max_drawdown: float | None


class StressTestResponse(BaseModel):
    scenarios: list[StressScenario]


class CustomStressRequest(BaseModel):
    start: str
    end: str
    name: str = "custom"


class GarchAssetParams(BaseModel):
    ticker: str
    alpha: float
    beta: float
    omega: float
    persistent: bool
    forecast_annual_vol: float


class GarchResponse(BaseModel):
    historical_vol: float
    forecast_vol: float
    forecast_band_low: float
    forecast_band_high: float
    history: list[dict[str, float | str]]  # {date, realised, garch}
    forward: list[dict[str, float | str]]  # {day, forecast, low, high}
    assets: list[GarchAssetParams]
    persistent_assets: list[str]


class LiquidityPosition(BaseModel):
    ticker: str
    current_weight: float
    position_usd: float
    adv_usd: float
    pct_of_adv: float
    days_to_liquidate_10: float
    days_to_liquidate_20: float
    days_to_liquidate_33: float
    liquidity_score: int
    kelly_weight: float
    kelly_half_weight: float
    kelly_divergence: float


class LiquidityResponse(BaseModel):
    aum: float
    positions: list[LiquidityPosition]


class CommentaryRequest(BaseModel):
    """Payload for /api/commentary/generate."""

    metrics: dict[str, Any]
    module: str = "overview"


class CommentaryResponse(BaseModel):
    """Claude-generated risk commentary."""

    commentary: str
    generated_at: str
    model: str
