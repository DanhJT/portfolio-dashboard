"""Historical stress-test replay."""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

SCENARIOS: dict[str, tuple[str, str]] = {
    "GFC_peak_to_trough": ("2008-09-01", "2009-03-09"),
    "COVID_crash":        ("2020-02-19", "2020-03-23"),
    "dot_com_bust":       ("2000-03-24", "2002-10-09"),
    "rate_shock_2022":    ("2022-01-03", "2022-10-12"),
}


def _fetch_window(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    """Daily adjusted closes for a window. Missing tickers become NaN columns."""
    raw = yf.download(
        tickers=tickers,
        start=start,
        end=end,
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=True,
        group_by="column",
    )
    if raw.empty:
        return pd.DataFrame(columns=tickers)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw["Close"].copy()
    else:
        close = raw[["Close"]].copy()
        close.columns = [tickers[0]]
    # Ensure all requested tickers appear as columns (missing become all-NaN).
    for t in tickers:
        if t not in close.columns:
            close[t] = np.nan
    return close[tickers]


def _scenario_metrics(
    prices: pd.DataFrame, weights: list[float]
) -> tuple[float | None, float | None, float | None]:
    """(portfolio_return, worst_day, max_drawdown) — None when data is missing."""
    if prices.empty or prices.isna().all().all():
        return None, None, None

    rets = prices.pct_change().dropna(how="all")
    if rets.empty:
        return None, None, None

    w = np.asarray(weights, dtype=float)
    # Re-normalise across the columns we actually have so partial-data scenarios
    # (e.g. NVDA didn't exist in 2000) still produce a comparable number.
    available_mask = ~rets.isna().all(axis=0).values
    if not available_mask.any():
        return None, None, None
    w_eff = w * available_mask
    s = w_eff.sum()
    if s <= 0:
        return None, None, None
    w_eff = w_eff / s

    # Drop columns that are all-NaN and align weights.
    cols = list(rets.columns)
    keep_cols = [c for c, a in zip(cols, available_mask) if a]
    w_aligned = np.array([w[cols.index(c)] for c in keep_cols], dtype=float)
    w_aligned = w_aligned / w_aligned.sum()
    rets_filled = rets[keep_cols].fillna(0.0)

    port_daily = rets_filled.values @ w_aligned
    if port_daily.size == 0:
        return None, None, None
    cum = np.cumprod(1.0 + port_daily)
    total_return = float(cum[-1] - 1.0)
    worst_day = float(port_daily.min())
    peak = np.maximum.accumulate(cum)
    drawdown = cum / peak - 1.0
    max_dd = float(drawdown.min())
    return total_return, worst_day, max_dd


def run_scenario(
    name: str, tickers: list[str], weights: list[float], start: str, end: str
) -> dict[str, object]:
    """Run a single window and return the standardised metrics dict."""
    prices = _fetch_window(tickers, start, end)
    pr, wd, dd = _scenario_metrics(prices, weights)
    return {
        "name": name,
        "start": start,
        "end": end,
        "portfolio_return": pr,
        "worst_day": wd,
        "max_drawdown": dd,
    }


def run_all_scenarios(
    tickers: list[str], weights: list[float]
) -> list[dict[str, object]]:
    """Run every preset scenario; returns one row per scenario."""
    out: list[dict[str, object]] = []
    for name, (s, e) in SCENARIOS.items():
        try:
            out.append(run_scenario(name, tickers, weights, s, e))
        except Exception as exc:  # noqa: BLE001
            logger.warning("scenario %s failed: %s", name, exc)
            out.append({
                "name": name, "start": s, "end": e,
                "portfolio_return": None, "worst_day": None, "max_drawdown": None,
            })
    return out
