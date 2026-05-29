"""Pre-compute and cache heavy analytics into app.state.cache.

Called at startup (as a background task) and after each monthly rebalance.
Monte Carlo, GARCH, stress tests, and liquidity are all computed once and
served instantly from memory on every subsequent request.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import numpy as np

from services import garch, liquidity, market_data, monte_carlo, stress_test

logger = logging.getLogger(__name__)

LOOKBACK = "2y"


async def precompute_all(app: Any) -> None:
    """Run all heavy analytics concurrently and store in app.state.cache."""
    portfolio = getattr(app.state, "portfolio", None)
    if not portfolio:
        logger.warning("precompute_all: no portfolio in app.state; skipping")
        return

    tickers: list[str] = list(portfolio["tickers"])
    weights: list[float] = list(portfolio["weights"])
    portfolio_key = ",".join(f"{t}:{w:.6f}" for t, w in zip(tickers, weights))

    logger.info("precompute starting for %s", tickers)

    try:
        prices = await market_data.fetch_prices(tickers, period=LOOKBACK)
    except Exception as exc:
        logger.error("precompute: price fetch failed — %s", exc)
        return

    returns = prices.pct_change().dropna(how="all")
    cols = list(returns.columns)
    wmap = dict(zip(tickers, weights))
    w = np.array([wmap.get(c, 0.0) for c in cols], dtype=float)
    if w.sum() > 0:
        w = w / w.sum()

    async def timed(label: str, coro):
        t0 = time.perf_counter()
        try:
            res = await coro
            logger.info("precompute %s done in %.1fs", label, time.perf_counter() - t0)
            return res
        except Exception as exc:
            logger.warning("precompute %s failed after %.1fs: %s", label, time.perf_counter() - t0, exc)
            return exc

    mc_r, garch_r, stress_r, liq_r = await asyncio.gather(
        timed("monte_carlo",  asyncio.to_thread(monte_carlo.simulate_portfolio_paths, returns, w)),
        timed("garch",        asyncio.to_thread(garch.portfolio_garch_vol_forecast, returns, w)),
        timed("stress_tests", asyncio.to_thread(stress_test.run_all_scenarios, tickers, weights)),
        timed("liquidity",    liquidity.liquidity_analysis(tickers, weights)),
        return_exceptions=True,
    )

    def _ok(label: str, result: Any) -> Any | None:
        if isinstance(result, Exception):
            logger.warning("precompute %s failed: %s", label, result)
            return None
        return result

    app.state.cache = {
        "monte_carlo":  _ok("monte_carlo", mc_r),
        "garch":        _ok("garch", garch_r),
        "stress_tests": _ok("stress_tests", stress_r),
        "liquidity":    _ok("liquidity", liq_r),
        "portfolio_key": portfolio_key,
    }
    logger.info(
        "precompute complete — MC:%s GARCH:%s stress:%s liq:%s",
        "ok" if app.state.cache["monte_carlo"]  else "err",
        "ok" if app.state.cache["garch"]        else "err",
        "ok" if app.state.cache["stress_tests"] else "err",
        "ok" if app.state.cache["liquidity"]    else "err",
    )
