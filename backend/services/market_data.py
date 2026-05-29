"""Market data fetching via yfinance.

Wraps yfinance with light caching, graceful handling of delisted tickers,
and consistent column ordering so downstream risk calculations don't have
to defend against missing or out-of-order columns.
"""
from __future__ import annotations

import logging
from datetime import datetime
from functools import lru_cache

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

_PERIOD_ALIASES: dict[str, str] = {
    "3m": "3mo",
    "3mo": "3mo",
    "6m": "6mo",
    "6mo": "6mo",
    "1y": "1y",
    "2y": "2y",
}


def normalise_period(period: str) -> str:
    """Map user-friendly period strings to yfinance period strings."""
    key = period.lower().strip()
    if key not in _PERIOD_ALIASES:
        raise ValueError(f"unsupported period '{period}'. Use one of: 3M, 6M, 1Y, 2Y")
    return _PERIOD_ALIASES[key]


@lru_cache(maxsize=64)
def _download_cached(tickers_key: str, period: str, stamp: str) -> pd.DataFrame:
    """Cached yfinance download. `stamp` invalidates cache per day."""
    tickers = tickers_key.split(",")
    logger.info("fetching %s prices for %s (stamp=%s)", period, tickers, stamp)
    raw = yf.download(
        tickers=tickers,
        period=period,
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=True,
        group_by="column",
    )
    if raw.empty:
        raise ValueError(f"no price data returned for {tickers}")

    # yfinance returns a multi-index when multiple tickers are requested.
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw["Close"].copy()
    else:
        # Single ticker: yfinance returns a flat frame.
        close = raw[["Close"]].copy()
        close.columns = [tickers[0]]

    # Preserve the caller's ticker order.
    ordered = [t for t in tickers if t in close.columns]
    close = close[ordered]
    return close


async def fetch_prices(tickers: list[str], period: str = "1y") -> pd.DataFrame:
    """Fetch daily adjusted close prices for the given tickers.

    Args:
        tickers: Ticker symbols, e.g. ["AAPL", "MSFT"].
        period: Lookback period; one of 3mo, 6mo, 1y, 2y (case-insensitive).

    Returns:
        DataFrame indexed by date with one column per ticker. Missing days
        are forward-filled and then back-filled so risk calcs receive a
        dense matrix. Delisted tickers with no data are dropped with a log
        warning rather than raising.
    """
    if not tickers:
        raise ValueError("tickers must be non-empty")

    yf_period = normalise_period(period)
    tickers_key = ",".join(sorted(set(tickers)))
    # 1-minute stamp: refresh feels live, but back-to-back clicks reuse data.
    stamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M")
    close = _download_cached(tickers_key, yf_period, stamp)

    # Re-project onto the originally requested order.
    available = [t for t in tickers if t in close.columns]
    dropped = [t for t in tickers if t not in close.columns]
    if dropped:
        logger.warning("dropping tickers with no data: %s", dropped)
    close = close[available]

    # Drop columns that are entirely NaN (delisted / bad symbol).
    fully_empty = close.columns[close.isna().all()].tolist()
    if fully_empty:
        logger.warning("dropping tickers with all-NaN price series: %s", fully_empty)
        close = close.drop(columns=fully_empty)

    close = close.ffill().bfill().dropna(how="any")
    if close.empty:
        raise ValueError("price frame empty after cleaning")
    return close


async def fetch_with_benchmark(
    tickers: list[str], period: str = "1y", benchmark: str = "SPY"
) -> tuple[pd.DataFrame, pd.Series]:
    """Fetch portfolio prices and a benchmark series aligned on the same dates."""
    combined = await fetch_prices([*tickers, benchmark], period=period)
    if benchmark not in combined.columns:
        raise ValueError(f"benchmark {benchmark} unavailable")
    bench = combined[benchmark]
    portfolio_prices = combined.drop(columns=[benchmark])
    return portfolio_prices, bench
