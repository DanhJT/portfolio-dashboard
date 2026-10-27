#!/usr/bin/env python3
"""Generate a complete static snapshot of the dashboard's data.

This is the engine behind the "fully static" deployment. It runs the exact
same strategy + analytics the live API would, then serialises everything the
frontend needs into ``frontend/public/snapshot.json``. The frontend (in static
mode) reads that file directly from Vercel's CDN, so no live backend — and no
request-time yfinance call — is needed in production.

Design notes
------------
- Performance (metrics + cumulative return per period) comes from a monthly
  backtest of the current rules (services/strategy.py), not from replaying
  today's holdings backwards. The live holdings are the backtest's latest
  rebalance, so the two always agree.
- Forward-looking risk (Monte Carlo, GARCH, stress tests, liquidity, news)
  describes today's holdings and reuses the routers' service functions and
  Pydantic models.
- The value signal needs SEC filings (SEC_CONTACT_EMAIL). If that data is
  unavailable the run fails rather than publishing a momentum-only portfolio,
  unless ALLOW_MOMENTUM_ONLY=1.
- The snapshot is only written if it is valid (portfolio, 1y period, backtest).
  On failure the script exits non-zero and leaves any existing snapshot
  untouched — a bad data day can never publish an empty file.

Usage
-----
    cd backend && python generate_snapshot.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, TypeVar

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from models.schemas import (
    ActivePortfolio,
    GarchAssetParams,
    GarchResponse,
    HoldingMetrics,
    LiquidityPosition,
    LiquidityResponse,
    MonteCarloResponse,
    NewsItem,
    NewsResponse,
    PricePoint,
    PriceSeriesResponse,
    RiskMetrics,
    StressScenario,
    StressTestResponse,
)
from services import (
    claude_client,
    fundamentals,
    garch,
    liquidity,
    market_data,
    monte_carlo,
    news,
    risk,
    strategy,
    stress_test,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("generate_snapshot")

PERIODS = ["3mo", "6mo", "1y", "2y", "5y"]
PERIOD_OFFSETS = {
    "3mo": pd.DateOffset(months=3),
    "6mo": pd.DateOffset(months=6),
    "1y": pd.DateOffset(years=1),
    "2y": pd.DateOffset(years=2),
    "5y": pd.DateOffset(years=5),
}
NEWS_TICKERS = 12
LOOKBACK = "2y"
DEFAULT_AUM = 1_000_000.0
SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "frontend" / "public" / "snapshot.json"

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

async def _retry(
    label: str,
    fn: Callable[[], Awaitable[T]],
    *,
    attempts: int = 4,
    base_delay: float = 3.0,
) -> T:
    """Run an async factory with exponential backoff. Re-raises on final fail."""
    last: Exception | None = None
    for i in range(1, attempts + 1):
        try:
            return await fn()
        except Exception as exc:  # noqa: BLE001 — yfinance errors come in many shapes
            last = exc
            if i < attempts:
                delay = base_delay * (2 ** (i - 1))
                logger.warning("%s failed (attempt %d/%d): %s — retrying in %.0fs",
                               label, i, attempts, exc, delay)
                await asyncio.sleep(delay)
    assert last is not None
    logger.error("%s failed after %d attempts: %s", label, attempts, last)
    raise last


# ---------------------------------------------------------------------------
# Section builders (each mirrors the corresponding router)
# ---------------------------------------------------------------------------

def _period_mask(index: pd.DatetimeIndex, period: str) -> np.ndarray:
    """Rows of the backtest that fall inside the trailing `period` window."""
    return index > index[-1] - PERIOD_OFFSETS[period]


def _metrics_section(run: strategy.StrategyRun, tickers: list[str],
                     weight_map: dict[str, float], period: str) -> dict[str, Any]:
    """Risk metrics of the backtested strategy over `period`.

    Portfolio-level numbers come from the backtest's daily returns (holdings
    change monthly). The per-holding rows describe today's holdings over the
    same window, which is what the holdings table is for.
    """
    mask = _period_mask(run.returns.index, period)
    port = run.returns[mask]
    bench = run.benchmark[mask]
    alpha, beta = risk.alpha_beta(port, bench)

    # One extra row in front so the first in-window day has a return.
    first = max(int(np.argmax(mask)) - 1, 0)
    window = run.returns.index[first:]
    hp = run.adj_close.reindex(columns=tickers).loc[window[0]:window[-1]].ffill().bfill()
    hp = hp.dropna(axis=1, how="all")
    hrets = risk.daily_returns(hp)
    contribs = risk.volatility_contributions(hp, weight_map) if not hp.empty else {}
    holdings = [
        HoldingMetrics(
            ticker=t,
            weight=float(weight_map.get(t, 0.0)),
            annualised_return=risk.annualised_return(hrets[t]),
            annualised_volatility=risk.annualised_volatility(hrets[t]),
            volatility_contribution=float(contribs.get(t, 0.0)),
        )
        for t in hp.columns
    ]
    model = RiskMetrics(
        annualised_return=risk.annualised_return(port),
        annualised_volatility=risk.annualised_volatility(port),
        sharpe_ratio=risk.sharpe_ratio(port),
        max_drawdown=risk.max_drawdown(port),
        var_95=risk.value_at_risk(port),
        cvar_95=risk.conditional_var(port),
        alpha=alpha,
        beta=beta,
        holdings=holdings,
        start_date=port.index[0].date(),
        end_date=port.index[-1].date(),
    )
    return model.model_dump(mode="json")


def _prices_section(run: strategy.StrategyRun, period: str) -> dict[str, Any]:
    """Cumulative return of the backtest vs the benchmark over `period`."""
    mask = _period_mask(run.returns.index, period)
    port_curve = risk.cumulative_curve(run.returns[mask])
    bench_curve = risk.cumulative_curve(run.benchmark[mask])
    series = [
        PricePoint(date=ts.date(), portfolio=float(port_curve.loc[ts]),
                   benchmark=float(bench_curve.loc[ts]))
        for ts in port_curve.index
    ]
    return PriceSeriesResponse(series=series, benchmark_ticker=strategy.BENCHMARK).model_dump(mode="json")


def _backtest_section(run: strategy.StrategyRun) -> dict[str, Any]:
    """How the backtest was run, and what every rebalance held."""
    rbs = run.rebalances
    rows = []
    prev: set[str] = set()
    for rb in rbs:
        names = list(rb.weights.index)
        rows.append({
            "date": rb.date.date().isoformat(),
            "strategy": rb.strategy,
            "ranked": rb.ranked,
            "n_holdings": len(names),
            "value_coverage": round(rb.value_coverage, 4),
            "turnover": round(rb.turnover, 4),
            "max_weight": round(float(rb.weights.max()), 4),
            "added": sorted(set(names) - prev) if prev else [],
            "removed": sorted(prev - set(names)) if prev else [],
            "holdings": {t: round(float(w), 5) for t, w in rb.weights.items()},
        })
        prev = set(names)
    later = rbs[1:]
    return {
        "start": run.returns.index[0].date().isoformat(),
        "end": run.returns.index[-1].date().isoformat(),
        "rules": {
            "selection_pct": strategy.SELECTION_PCT,
            "min_holdings": strategy.MIN_HOLDINGS,
            "weight_cap": strategy.WEIGHT_CAP,
            "reporting_lag_days": fundamentals.REPORTING_LAG.days,
            "backtest_years": strategy.BACKTEST_YEARS,
            "benchmark": strategy.BENCHMARK,
        },
        "summary": {
            "rebalances": len(rbs),
            "avg_holdings": round(float(np.mean([len(r.weights) for r in rbs])), 1),
            "avg_turnover": round(float(np.mean([r.turnover for r in later])), 4) if later else None,
            "value_momentum_months": sum(r.strategy == "value-momentum" for r in rbs),
            "momentum_only_months": sum(r.strategy == "momentum" for r in rbs),
            "avg_value_coverage": round(float(np.mean([r.value_coverage for r in rbs])), 4),
            "max_weight_ever": round(float(max(r.weights.max() for r in rbs)), 4),
        },
        "rebalances": rows,
    }


def _aligned_returns_and_weights(tickers: list[str], weights: list[float]):
    """Replicate the precompute weight-alignment step (returns, w-vector)."""
    async def _go():
        prices = await market_data.fetch_prices(tickers, period=LOOKBACK)
        returns = prices.pct_change().dropna(how="all")
        cols = list(returns.columns)
        wmap = dict(zip(tickers, weights))
        w = np.array([wmap.get(c, 0.0) for c in cols], dtype=float)
        if w.sum() > 0:
            w = w / w.sum()
        return returns, w

    return asyncio.run(_retry("returns[2y]", _go))


def _monte_carlo_section(returns, w) -> dict[str, Any]:
    result = monte_carlo.simulate_portfolio_paths(returns, w)
    return MonteCarloResponse(**result).model_dump(mode="json")


def _garch_section(returns, w) -> dict[str, Any]:
    result = garch.portfolio_garch_vol_forecast(returns, w)
    return GarchResponse(
        historical_vol=result["historical_vol"],
        forecast_vol=result["forecast_vol"],
        forecast_band_low=result["forecast_band_low"],
        forecast_band_high=result["forecast_band_high"],
        history=result["history"],
        forward=result["forward"],
        assets=[GarchAssetParams(**a) for a in result["assets"]],
        persistent_assets=result["persistent_assets"],
    ).model_dump(mode="json")


def _stress_section(tickers: list[str], weights: list[float]) -> dict[str, Any]:
    rows = stress_test.run_all_scenarios(tickers, weights)
    return StressTestResponse(
        scenarios=[StressScenario(**r) for r in rows]
    ).model_dump(mode="json")


def _liquidity_section(tickers: list[str], weights: list[float]) -> dict[str, Any]:
    async def _go() -> dict[str, Any]:
        result = await liquidity.liquidity_analysis(tickers, weights, aum=DEFAULT_AUM)
        return LiquidityResponse(
            aum=result["aum"],
            positions=[LiquidityPosition(**p) for p in result["positions"]],
        ).model_dump(mode="json")

    return asyncio.run(_retry("liquidity", _go))


def _news_section(tickers: list[str]) -> dict[str, Any]:
    async def _go() -> dict[str, Any]:
        raw = await news.fetch_news(tickers)
        return NewsResponse(items=[NewsItem(**item) for item in raw]).model_dump(mode="json")

    # News is best-effort: an empty list is acceptable, so don't abort the run.
    try:
        return asyncio.run(_retry("news", _go, attempts=2))
    except Exception as exc:  # noqa: BLE001
        logger.warning("news unavailable, continuing with empty list: %s", exc)
        return {"items": []}


def _commentary_section(metrics_1y: dict, mc: dict | None, stress: dict | None,
                        garch_d: dict | None, liq: dict | None) -> dict[str, Any]:
    """Precompute rule-based commentary for each module the UI can request."""
    async def _gen(payload: dict, module: str) -> dict[str, Any]:
        text, ts = await claude_client.generate_commentary(payload, module=module)
        return {"commentary": text, "generated_at": ts, "model": claude_client.MODEL}

    out: dict[str, Any] = {}
    try:
        out["overview"] = asyncio.run(_gen(metrics_1y, "overview"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("overview commentary failed: %s", exc)
    if mc is not None or stress is not None or garch_d is not None:
        try:
            payload = {
                "monte_carlo": mc or {},
                "stress_tests": (stress or {}).get("scenarios", []),
                "garch": garch_d or {},
            }
            out["risk"] = asyncio.run(_gen(payload, "risk"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("risk commentary failed: %s", exc)
    if liq is not None:
        try:
            out["liquidity"] = asyncio.run(_gen(liq, "liquidity"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("liquidity commentary failed: %s", exc)
    return out


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def build_snapshot() -> dict[str, Any]:
    t0 = time.perf_counter()

    # Every rebalance, past and current, comes from the same rules, so the
    # live holdings are just the latest rebalance of a fresh backtest. Past
    # rebalances only use data from before their date, so re-running daily
    # reproduces them; between month starts the holdings don't change.
    run = strategy.run_strategy()
    if run.notes and os.environ.get("ALLOW_MOMENTUM_ONLY") != "1":
        # Publishing momentum-only holdings would quietly change the strategy.
        raise RuntimeError("; ".join(run.notes) + " (set ALLOW_MOMENTUM_ONLY=1 to publish anyway)")
    portfolio = strategy.portfolio_from_run(run)

    tickers = list(portfolio["tickers"])
    weights = list(portfolio["weights"])
    weight_map = dict(zip(tickers, weights))
    logger.info("portfolio: %d names (%s) rebalanced_at %s",
                len(tickers), portfolio["strategy"], portfolio["rebalanced_at"])

    periods: dict[str, Any] = {}
    for p in PERIODS:
        periods[p] = {
            "metrics": _metrics_section(run, tickers, weight_map, p),
            "prices": _prices_section(run, p),
        }

    # Forward-looking risk analytics describe today's holdings.
    logger.info("fetching 2y returns for analytics…")
    returns, w = _aligned_returns_and_weights(tickers, weights)

    def _safe(label: str, fn: Callable[[], dict]) -> dict | None:
        try:
            res = fn()
            logger.info("%s done", label)
            return res
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s failed: %s", label, exc)
            return None

    mc = _safe("monte_carlo", lambda: _monte_carlo_section(returns, w))
    garch_d = _safe("garch", lambda: _garch_section(returns, w))
    stress = _safe("stress_tests", lambda: _stress_section(tickers, weights))
    liq = _safe("liquidity", lambda: _liquidity_section(tickers, weights))
    # News for the largest positions only; ~50 names would flood the panel.
    news_d = _news_section(sorted(tickers, key=lambda t: -weight_map[t])[:NEWS_TICKERS])

    commentary = _commentary_section(periods["1y"]["metrics"], mc, stress, garch_d, liq)

    snapshot = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "portfolio": ActivePortfolio(**portfolio).model_dump(mode="json"),
        "periods": periods,
        "backtest": _backtest_section(run),
        "news": news_d,
        "monte_carlo": mc,
        "stress_tests": stress,
        "garch": garch_d,
        "liquidity": liq,
        "commentary": commentary,
    }
    logger.info("snapshot built in %.1fs", time.perf_counter() - t0)
    return snapshot


def _is_valid(snapshot: dict[str, Any]) -> bool:
    """A snapshot is publishable only if it has a portfolio and the 1y period."""
    portfolio = snapshot.get("portfolio") or {}
    if not portfolio.get("tickers") or not portfolio.get("weights"):
        logger.error("validation failed: empty portfolio")
        return False
    one_year = (snapshot.get("periods") or {}).get("1y") or {}
    if not one_year.get("metrics") or not one_year.get("prices"):
        logger.error("validation failed: missing 1y metrics/prices")
        return False
    if not (snapshot.get("backtest") or {}).get("rebalances"):
        logger.error("validation failed: missing backtest")
        return False
    return True


def main() -> int:
    try:
        snapshot = build_snapshot()
    except Exception as exc:  # noqa: BLE001
        logger.error("snapshot generation crashed: %s", exc)
        return 1

    if not _is_valid(snapshot):
        logger.error("snapshot invalid — leaving existing file untouched")
        return 1

    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = SNAPSHOT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(snapshot, indent=2))
    tmp.replace(SNAPSHOT_PATH)
    logger.info("wrote %s (%.1f KB)", SNAPSHOT_PATH, SNAPSHOT_PATH.stat().st_size / 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
