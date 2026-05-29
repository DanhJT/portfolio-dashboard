"""Liquidity + Kelly-sizing analytics."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

from services import market_data

logger = logging.getLogger(__name__)

ADV_LOOKBACK_DAYS = 30
RISK_FREE_RATE = 0.045
TRADING_DAYS = 252


def _liquidity_score(adv_usd: float) -> int:
    """5 = ADV > $100M  →  1 = ADV < $100K."""
    if adv_usd > 100_000_000:
        return 5
    if adv_usd > 10_000_000:
        return 4
    if adv_usd > 1_000_000:
        return 3
    if adv_usd > 100_000:
        return 2
    return 1


def _fetch_volume_and_price(ticker: str) -> tuple[str, float | None, float | None]:
    """Return (ticker, 30-day average $ volume, latest close) or (ticker, None, None)."""
    try:
        df = yf.Ticker(ticker).history(period="3mo", interval="1d")
    except Exception as exc:  # noqa: BLE001
        logger.debug("liquidity fetch failed for %s: %s", ticker, exc)
        return ticker, None, None
    if df.empty:
        return ticker, None, None
    df = df.dropna(subset=["Close", "Volume"])
    if df.empty:
        return ticker, None, None
    recent = df.tail(ADV_LOOKBACK_DAYS)
    dollar_vol = (recent["Volume"] * recent["Close"]).mean()
    last_close = float(df["Close"].iloc[-1])
    if not np.isfinite(dollar_vol) or not np.isfinite(last_close):
        return ticker, None, None
    return ticker, float(dollar_vol), last_close


def _kelly_weights(returns: pd.DataFrame, rf: float = RISK_FREE_RATE) -> pd.Series:
    """f* = (μ − rf) / σ² per asset, computed from annualised stats."""
    mu = returns.mean() * TRADING_DAYS
    var = (returns.std(ddof=1) * np.sqrt(TRADING_DAYS)) ** 2
    f = (mu - rf) / var.replace(0, np.nan)
    return f.fillna(0.0).clip(lower=0.0)


async def liquidity_analysis(
    tickers: list[str],
    weights: list[float],
    aum: float = 1_000_000.0,
) -> dict[str, Any]:
    """Build the per-position liquidity + Kelly view."""
    # Volume + price (network-bound) in parallel.
    vol_results = await asyncio.gather(
        *(asyncio.to_thread(_fetch_volume_and_price, t) for t in tickers)
    )
    vol_map: dict[str, float] = {}
    for ticker, adv, _ in vol_results:
        if adv is not None:
            vol_map[ticker] = adv

    # Kelly weights need 2 years of returns.
    prices = await market_data.fetch_prices(tickers, period="2y")
    returns = prices.pct_change().dropna(how="all")
    kelly_raw = _kelly_weights(returns)
    # Normalise the raw Kelly fractions to a target leverage of 1.0 for a
    # comparable "Kelly weight" alongside the current weights.
    kelly_total = float(kelly_raw.sum())
    if kelly_total > 0:
        kelly_norm = kelly_raw / kelly_total
    else:
        kelly_norm = pd.Series(1.0 / len(tickers), index=tickers)

    positions: list[dict[str, Any]] = []
    for ticker, weight in zip(tickers, weights):
        position_usd = aum * weight
        adv = vol_map.get(ticker)
        if adv is None or adv <= 0:
            adv = 1.0  # avoids division by zero; pct will be huge → flagged as illiquid
            score = 1
        else:
            score = _liquidity_score(adv)
        pct_of_adv = position_usd / adv
        kelly_w = float(kelly_norm.get(ticker, 0.0))
        positions.append({
            "ticker": ticker,
            "current_weight": float(weight),
            "position_usd": float(position_usd),
            "adv_usd": float(adv),
            "pct_of_adv": float(pct_of_adv),
            "days_to_liquidate_10": float(pct_of_adv / 0.10),
            "days_to_liquidate_20": float(pct_of_adv / 0.20),
            "days_to_liquidate_33": float(pct_of_adv / 0.33),
            "liquidity_score": int(score),
            "kelly_weight": kelly_w,
            "kelly_half_weight": kelly_w * 0.5,
            "kelly_divergence": float(kelly_w - weight),
        })

    return {"aum": float(aum), "positions": positions}
