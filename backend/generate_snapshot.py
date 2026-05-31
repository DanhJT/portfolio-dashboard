#!/usr/bin/env python3
"""Generate a complete static snapshot of the dashboard's data.

This is the engine behind the "fully static" deployment. It runs the exact
same strategy + analytics the live API would, then serialises everything the
frontend needs into ``frontend/public/snapshot.json``. The frontend (in static
mode) reads that file directly from Vercel's CDN, so no live backend — and no
request-time yfinance call — is needed in production.

Design notes
------------
- Output mirrors the live API responses **field-for-field**: every section is
  built by reusing the same service functions the routers use and dumped via
  the same Pydantic models, so the frontend needs no changes.
- yfinance is rate-limited from datacenter IPs, so each network-bound step is
  wrapped in retry-with-backoff. The strategy itself degrades gracefully
  (momentum-only, then equal-weight) and never raises.
- The snapshot is only written if it is valid (non-empty portfolio + at least
  the 1y period). On failure the script exits non-zero and leaves any existing
  snapshot untouched — a bad data day can never publish an empty file.

Usage
-----
    cd backend && python generate_snapshot.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, TypeVar

import numpy as np

from models.schemas import (
    ActivePortfolio,
    CorrelationResponse,
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
    garch,
    liquidity,
    market_data,
    monte_carlo,
    news,
    risk,
    stress_test,
)
from scheduler import _is_first_trading_day_of_month
from services.strategy import run_value_momentum_strategy

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("generate_snapshot")

PERIODS = ["3mo", "6mo", "1y", "2y"]
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

def _metrics_section(tickers: list[str], weight_map: dict[str, float], period: str) -> dict[str, Any]:
    """Mirror routers/portfolio.py::get_metrics."""
    async def _go() -> dict[str, Any]:
        prices, bench = await market_data.fetch_with_benchmark(tickers, period=period)
        bench = bench if not bench.empty else None
        m = risk.compute_portfolio_metrics(prices, weight_map, benchmark=bench)
        model = RiskMetrics(
            annualised_return=m.annualised_return,
            annualised_volatility=m.annualised_volatility,
            sharpe_ratio=m.sharpe_ratio,
            max_drawdown=m.max_drawdown,
            var_95=m.var_95,
            cvar_95=m.cvar_95,
            alpha=m.alpha,
            beta=m.beta,
            holdings=[
                HoldingMetrics(
                    ticker=h.ticker,
                    weight=h.weight,
                    annualised_return=h.annualised_return,
                    annualised_volatility=h.annualised_volatility,
                    volatility_contribution=h.volatility_contribution,
                )
                for h in m.holdings
            ],
            start_date=m.start_date.date(),
            end_date=m.end_date.date(),
        )
        return model.model_dump(mode="json")

    return asyncio.run(_retry(f"metrics[{period}]", _go))


def _prices_section(tickers: list[str], weight_map: dict[str, float], period: str,
                    benchmark: str = "SPY") -> dict[str, Any]:
    """Mirror routers/portfolio.py::get_prices."""
    async def _go() -> dict[str, Any]:
        prices, bench = await market_data.fetch_with_benchmark(
            tickers, period=period, benchmark=benchmark
        )
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
        return PriceSeriesResponse(series=series, benchmark_ticker=benchmark).model_dump(mode="json")

    return asyncio.run(_retry(f"prices[{period}]", _go))


def _correlation_section(tickers: list[str], period: str) -> dict[str, Any]:
    """Mirror routers/portfolio.py::get_correlation."""
    async def _go() -> dict[str, Any]:
        prices = await market_data.fetch_prices(tickers, period=period)
        corr = risk.correlation_matrix(prices)
        return CorrelationResponse(
            tickers=list(corr.columns),
            matrix=[[float(v) for v in row] for row in corr.values],
        ).model_dump(mode="json")

    return asyncio.run(_retry(f"correlation[{period}]", _go))


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

def _load_existing_rebalanced_at() -> str | None:
    """Read rebalanced_at from the existing snapshot, if any."""
    try:
        if SNAPSHOT_PATH.exists():
            existing = json.loads(SNAPSHOT_PATH.read_text())
            return existing.get("portfolio", {}).get("rebalanced_at")
    except Exception:  # noqa: BLE001
        pass
    return None


def build_snapshot() -> dict[str, Any]:
    t0 = time.perf_counter()
    from datetime import date, datetime, timezone

    today = date.today()
    is_rebalance_day = _is_first_trading_day_of_month(today)

    # Determine the correct rebalanced_at:
    # - On a genuine rebalance day (first trading day of the month): stamp today.
    # - Any other day: preserve the date from the existing snapshot so the UI
    #   shows when the portfolio was actually last rebalanced, not when the
    #   snapshot was regenerated.
    if is_rebalance_day:
        rebalanced_at = datetime.combine(today, datetime.min.time()).replace(
            tzinfo=timezone.utc
        ).isoformat()
        logger.info("today is a rebalance day (%s) — running fresh strategy", today)
    else:
        rebalanced_at = _load_existing_rebalanced_at()
        logger.info(
            "not a rebalance day (%s) — preserving existing rebalanced_at: %s",
            today,
            rebalanced_at,
        )

    logger.info("running strategy…")
    portfolio = run_value_momentum_strategy(rebalanced_at=rebalanced_at)
    tickers = list(portfolio["tickers"])
    weights = list(portfolio["weights"])
    weight_map = dict(zip(tickers, weights))
    logger.info("portfolio: %s (%s) rebalanced_at: %s", tickers, portfolio["strategy"],
                portfolio["rebalanced_at"])

    # Per-period metrics / prices / correlation.
    periods: dict[str, Any] = {}
    for p in PERIODS:
        logger.info("building period %s…", p)
        periods[p] = {
            "metrics": _metrics_section(tickers, weight_map, p),
            "prices": _prices_section(tickers, weight_map, p),
            "correlation": _correlation_section(tickers, p),
        }

    # Heavy analytics (2y lookback, computed once like precompute_all).
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
    news_d = _news_section(tickers)

    commentary = _commentary_section(periods["1y"]["metrics"], mc, stress, garch_d, liq)

    snapshot = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "portfolio": ActivePortfolio(**portfolio).model_dump(mode="json"),
        "periods": periods,
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
