"""Live value-momentum strategy following Asness, Moskowitz & Pedersen (2013).

Signals
-------
- Momentum (Jegadeesh & Titman 1993): 12-1 price momentum. Total return from
  t-12 months to t-2 months — i.e. skip the most recent month so we don't
  pick up the one-month reversal effect.
- Value (Fama & French 1992): book-to-market = 1 / price-to-book.
- Composite: equal-weighted z-scores, each winsorised at ±3σ.

Portfolio construction
----------------------
- Top 5 names by composite score.
- Score-weighted: shift so the lowest selected score becomes 0, normalise to
  sum to 1.0, then iteratively cap each weight at 35% and redistribute the
  excess proportionally to the uncapped names.
- If anything goes wrong (network, missing data, degenerate signals), fall
  back to an equal-weighted basket of five large-cap defaults.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

UNIVERSE: list[str] = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "LLY", "JPM", "V", "UNH",
    "XOM", "MA", "JNJ", "PG", "HD", "AVGO", "COST", "MRK", "CVX", "ABBV",
    "WMT", "BAC", "CRM", "KO", "PEP", "ACN", "MCD", "TMO", "CSCO", "ABT",
    "ADBE", "NFLX", "WFC", "TXN", "DHR", "LIN", "PM", "AMD", "AMGN", "NEE",
    "RTX", "LOW", "INTU", "CAT", "SPGI", "ISRG", "GS", "BLK", "AMAT", "SYK",
]

TOP_N = 5
WEIGHT_CAP = 0.35
WINSOR_LIMIT = 3.0

# Equal-weight fallback basket: five large-cap names across distinct sectors,
# used when live signals can't be computed (e.g. data provider rate-limits us).
FALLBACK_TICKERS: list[str] = ["AAPL", "MSFT", "JPM", "JNJ", "XOM"]
TRADING_DAYS_PER_MONTH = 21
MOMENTUM_LOOKBACK_DAYS = 12 * TRADING_DAYS_PER_MONTH   # ~252
MOMENTUM_SKIP_DAYS = TRADING_DAYS_PER_MONTH            # ~21


# ---------------------------------------------------------------------------
# Signal computation
# ---------------------------------------------------------------------------

def _zscore_winsorise(series: pd.Series) -> pd.Series:
    """Cross-sectional z-score clipped to ±WINSOR_LIMIT."""
    s = series.dropna()
    if len(s) < 2:
        return pd.Series(dtype=float)
    std = s.std(ddof=1)
    if std == 0 or np.isnan(std):
        return pd.Series(0.0, index=s.index)
    z = (s - s.mean()) / std
    return z.clip(-WINSOR_LIMIT, WINSOR_LIMIT)


def _momentum_signal(tickers: list[str]) -> pd.Series:
    """12-1 price momentum z-score for each ticker. NaN for tickers missing data."""
    raw = yf.download(
        tickers=tickers,
        period="14mo",
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=True,
        group_by="column",
    )
    if raw.empty:
        raise RuntimeError("yfinance returned no momentum data")

    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    if not isinstance(close, pd.DataFrame):
        close = close.to_frame()

    # 12-1 return: price ~21 trading days ago divided by price ~252 trading days ago.
    if len(close) < MOMENTUM_LOOKBACK_DAYS + 1:
        raise RuntimeError(
            f"only {len(close)} daily bars available; need {MOMENTUM_LOOKBACK_DAYS + 1}"
        )
    end = close.iloc[-MOMENTUM_SKIP_DAYS]
    start = close.iloc[-MOMENTUM_LOOKBACK_DAYS]
    momentum = (end / start - 1.0).dropna()
    return _zscore_winsorise(momentum)


def _fetch_price_to_book(ticker: str) -> tuple[str, float | None]:
    """One ticker's P/B from yfinance Ticker.info. Returns None on failure."""
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception as exc:  # noqa: BLE001 — network errors come in many shapes
        logger.debug("value fetch failed for %s: %s", ticker, exc)
        return ticker, None
    pb = info.get("priceToBook")
    if pb is None or not isinstance(pb, (int, float)) or pb <= 0:
        return ticker, None
    return ticker, float(pb)


def _value_signal(tickers: list[str]) -> pd.Series:
    """Book-to-market z-score for each ticker. Drops missing/negative P/B."""
    pb_map: dict[str, float] = {}
    # yfinance Ticker.info is network-bound; parallelise so we don't wait minutes.
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(_fetch_price_to_book, t) for t in tickers]
        for fut in as_completed(futures):
            ticker, pb = fut.result()
            if pb is not None:
                pb_map[ticker] = pb
    if not pb_map:
        # Degrade gracefully: an empty value signal lets the caller fall back
        # to momentum-only rather than aborting the whole strategy.
        logger.warning("no price-to-book data available; value signal unavailable")
        return pd.Series(dtype=float)
    btm = pd.Series({t: 1.0 / pb for t, pb in pb_map.items()})
    return _zscore_winsorise(btm)


# ---------------------------------------------------------------------------
# Portfolio construction
# ---------------------------------------------------------------------------

def _apply_weight_cap(weights: pd.Series, cap: float) -> pd.Series:
    """Iteratively cap each weight and spread the excess across uncapped names."""
    w = weights.astype(float).copy()
    for _ in range(12):
        over = w > cap + 1e-9
        if not over.any():
            break
        excess = float((w[over] - cap).sum())
        w[over] = cap
        under = ~over
        under_sum = float(w[under].sum())
        if under_sum <= 0 or excess <= 0:
            break
        w[under] = w[under] + excess * (w[under] / under_sum)
    # Final renormalise to wash out any floating-point drift.
    total = float(w.sum())
    if total > 0:
        w = w / total
    return w


def _construct_weights(composite: pd.Series) -> pd.Series:
    """Pick top-N by composite, score-weight them, then apply the 35% cap.

    The lowest-ranked selected name still receives a meaningful allocation:
    we shift scores so the minimum is 0, then add a floor of (spread / N) so
    the bottom name has a baseline of roughly one Nth of the score range.
    Without this floor, the lowest-ranked selected ticker would have a
    "shifted" score of zero and therefore weight zero — collapsing the
    portfolio to N-1 effective positions. When all selected scores tie, the
    floor defaults to 1.0 and we get an equal-weight portfolio.
    """
    top = composite.nlargest(TOP_N).copy()
    spread = float(top.max() - top.min())
    floor = spread / TOP_N if spread > 0 else 1.0
    shifted = (top - top.min()) + floor
    weights = shifted / shifted.sum()
    return _apply_weight_cap(weights, WEIGHT_CAP)


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def _equal_weight_fallback() -> dict[str, Any]:
    """Equal-weight basket of large-cap defaults. Caller sets rebalanced_at."""
    n = len(FALLBACK_TICKERS)
    logger.warning("using equal-weight fallback basket: %s", FALLBACK_TICKERS)
    return {
        "tickers": list(FALLBACK_TICKERS),
        "weights": [1.0 / n] * n,
        "strategy": "equal-weight-fallback",
        "rebalanced_at": None,  # caller fills this in
    }


def run_value_momentum_strategy(rebalanced_at: str | None = None) -> dict[str, Any]:
    """Compute the live value-momentum portfolio.

    Args:
        rebalanced_at: ISO timestamp to use for the rebalanced_at field.
            Pass this when you want to preserve a known rebalance date (e.g.
            the snapshot generator passes the existing date on non-rebalance
            days). If None, stamps the current UTC time — only appropriate
            when this is called as a genuine rebalance event.

    Degrades in two steps so a data outage never crashes the caller:
    1. If the value signal is unavailable, fall back to momentum-only.
    2. If momentum (or anything else) fails, fall back to an equal-weight
       basket of large-cap defaults.
    """
    _rebalanced_at = rebalanced_at or datetime.now(timezone.utc).isoformat()
    try:
        mom = _momentum_signal(UNIVERSE)
        if mom.empty or len(mom) < TOP_N:
            raise RuntimeError(f"momentum signal yielded only {len(mom)} names")

        val = _value_signal(UNIVERSE)
        common = mom.index.intersection(val.index)
        if not val.empty and len(common) >= TOP_N:
            composite = 0.5 * mom.loc[common] + 0.5 * val.loc[common]
            strategy = "value-momentum"
        else:
            # Value data missing or too sparse to combine — use momentum alone.
            logger.warning(
                "value signal sparse (%d overlapping names); using momentum-only",
                len(common),
            )
            composite = mom
            strategy = "momentum"

        weights = _construct_weights(composite)
        result = {
            "tickers": list(weights.index),
            "weights": [float(w) for w in weights.values],
            "strategy": strategy,
            "rebalanced_at": _rebalanced_at,
        }
        logger.info(
            "%s strategy selected %s with weights %s",
            strategy,
            result["tickers"],
            [round(w, 4) for w in result["weights"]],
        )
        return result
    except Exception as exc:
        logger.error("strategy failed: %s — falling back to equal-weight defaults", exc)
        fb = _equal_weight_fallback()
        fb["rebalanced_at"] = _rebalanced_at
        return fb
