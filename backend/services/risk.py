"""Portfolio risk metrics.

All functions operate on a price DataFrame (rows = dates, columns = tickers)
and a weights mapping. Daily returns are simple percentage changes; annual
figures use 252 trading days. The risk-free rate is fixed at 4.5% to match
the spec; change `RISK_FREE_RATE` if you want to make it dynamic later.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

TRADING_DAYS = 252
RISK_FREE_RATE = 0.045
VAR_CONFIDENCE = 0.95


@dataclass(frozen=True)
class HoldingDiagnostic:
    """Per-position breakdown returned alongside the portfolio metrics."""

    ticker: str
    weight: float
    annualised_return: float
    annualised_volatility: float
    volatility_contribution: float


@dataclass(frozen=True)
class PortfolioMetrics:
    """Bundle of portfolio-level risk metrics."""

    annualised_return: float
    annualised_volatility: float
    sharpe_ratio: float
    max_drawdown: float
    var_95: float
    cvar_95: float
    alpha: float
    beta: float
    holdings: list[HoldingDiagnostic]
    portfolio_returns: pd.Series
    start_date: pd.Timestamp
    end_date: pd.Timestamp


def _weight_vector(weights: dict[str, float], columns: list[str]) -> np.ndarray:
    """Build a weight vector aligned to `columns`, renormalising if needed."""
    raw = np.array([weights.get(c, 0.0) for c in columns], dtype=float)
    s = raw.sum()
    if s <= 0:
        raise ValueError("weights sum to zero after alignment with price columns")
    return raw / s


def daily_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Simple daily returns; drops the first NaN row."""
    return prices.pct_change().dropna(how="all")


def portfolio_returns(prices: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """Weighted daily portfolio return series."""
    rets = daily_returns(prices)
    w = _weight_vector(weights, list(rets.columns))
    return pd.Series(rets.values @ w, index=rets.index, name="portfolio")


def annualised_return(returns: pd.Series) -> float:
    """Compound-annual growth rate implied by the daily return series."""
    if returns.empty:
        return 0.0
    total_growth = float((1.0 + returns).prod())
    years = len(returns) / TRADING_DAYS
    if years <= 0:
        return 0.0
    return total_growth ** (1.0 / years) - 1.0


def annualised_volatility(returns: pd.Series) -> float:
    """Std-dev of daily returns scaled by sqrt(252)."""
    if returns.empty:
        return 0.0
    return float(returns.std(ddof=1) * np.sqrt(TRADING_DAYS))


def sharpe_ratio(returns: pd.Series, rf: float = RISK_FREE_RATE) -> float:
    """Annualised Sharpe ratio. Uses arithmetic excess return over rf."""
    vol = annualised_volatility(returns)
    if vol == 0:
        return 0.0
    ann_ret = float(returns.mean() * TRADING_DAYS)
    return (ann_ret - rf) / vol


def max_drawdown(returns: pd.Series) -> float:
    """Worst peak-to-trough decline of the cumulative return curve. Negative."""
    if returns.empty:
        return 0.0
    curve = (1.0 + returns).cumprod()
    peak = curve.cummax()
    drawdown = curve / peak - 1.0
    return float(drawdown.min())


def value_at_risk(returns: pd.Series, confidence: float = VAR_CONFIDENCE) -> float:
    """Historical VaR at `confidence`. Positive number = expected loss magnitude."""
    if returns.empty:
        return 0.0
    quantile = returns.quantile(1.0 - confidence)
    return float(-quantile)


def conditional_var(returns: pd.Series, confidence: float = VAR_CONFIDENCE) -> float:
    """Expected shortfall: average loss beyond the VaR threshold."""
    if returns.empty:
        return 0.0
    threshold = returns.quantile(1.0 - confidence)
    tail = returns[returns <= threshold]
    if tail.empty:
        return float(-threshold)
    return float(-tail.mean())


def alpha_beta(
    portfolio_rets: pd.Series,
    benchmark_rets: pd.Series,
    rf: float = RISK_FREE_RATE,
) -> tuple[float, float]:
    """Jensen's alpha and market beta via OLS on daily excess returns.

    β = Cov(Rp - Rf/252, Rm - Rf/252) / Var(Rm - Rf/252)
    α = annualised intercept from the regression
    """
    aligned = pd.concat([portfolio_rets, benchmark_rets], axis=1).dropna()
    if aligned.empty or len(aligned) < 10:
        return 0.0, 1.0
    rf_daily = rf / TRADING_DAYS
    rp = aligned.iloc[:, 0] - rf_daily
    rm = aligned.iloc[:, 1] - rf_daily
    beta = float(rp.cov(rm) / rm.var(ddof=1)) if rm.var(ddof=1) > 0 else 1.0
    alpha = float((rp.mean() - beta * rm.mean()) * TRADING_DAYS)
    return alpha, beta


def correlation_matrix(prices: pd.DataFrame) -> pd.DataFrame:
    """Pearson correlation of daily returns between holdings."""
    return daily_returns(prices).corr()


def volatility_contributions(
    prices: pd.DataFrame, weights: dict[str, float]
) -> dict[str, float]:
    """Marginal contribution of each holding to portfolio variance, normalised.

    Returns a mapping ticker -> share of portfolio volatility (sums to ~1.0).
    Computed as w_i * (Sigma w)_i / (w' Sigma w).
    """
    rets = daily_returns(prices)
    cols = list(rets.columns)
    w = _weight_vector(weights, cols)
    cov = rets.cov().values * TRADING_DAYS
    port_var = float(w @ cov @ w)
    if port_var <= 0:
        return {c: 0.0 for c in cols}
    marginal = cov @ w
    contrib = w * marginal / port_var
    return {c: float(contrib[i]) for i, c in enumerate(cols)}


def compute_portfolio_metrics(
    prices: pd.DataFrame,
    weights: dict[str, float],
    benchmark: pd.Series | None = None,
) -> PortfolioMetrics:
    """Run the full risk suite on a price frame + weights mapping."""
    if prices.empty:
        raise ValueError("price frame is empty")

    rets = daily_returns(prices)
    port = portfolio_returns(prices, weights)
    contribs = volatility_contributions(prices, weights)

    bench_rets = benchmark.pct_change().dropna() if benchmark is not None else None
    a, b = alpha_beta(port, bench_rets) if bench_rets is not None else (0.0, 1.0)

    holdings: list[HoldingDiagnostic] = []
    for ticker in prices.columns:
        col_rets = rets[ticker]
        holdings.append(
            HoldingDiagnostic(
                ticker=ticker,
                weight=float(weights.get(ticker, 0.0)),
                annualised_return=annualised_return(col_rets),
                annualised_volatility=annualised_volatility(col_rets),
                volatility_contribution=contribs.get(ticker, 0.0),
            )
        )

    return PortfolioMetrics(
        annualised_return=annualised_return(port),
        annualised_volatility=annualised_volatility(port),
        sharpe_ratio=sharpe_ratio(port),
        max_drawdown=max_drawdown(port),
        var_95=value_at_risk(port),
        cvar_95=conditional_var(port),
        alpha=a,
        beta=b,
        holdings=holdings,
        portfolio_returns=port,
        start_date=port.index[0],
        end_date=port.index[-1],
    )


def cumulative_curve(returns: pd.Series) -> pd.Series:
    """Cumulative return curve starting at 0 (i.e. (1+r).cumprod() - 1)."""
    return (1.0 + returns).cumprod() - 1.0
