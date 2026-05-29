"""Per-asset GARCH(1,1) fitting + portfolio-level vol forecast."""
from __future__ import annotations

import logging
import warnings
from typing import Any

import numpy as np
import pandas as pd
from arch import arch_model

logger = logging.getLogger(__name__)

TRADING_DAYS = 252
PERSISTENCE_THRESHOLD = 0.95


def fit_garch(
    returns: pd.Series, horizon: int = 30
) -> dict[str, Any]:
    """Fit GARCH(1,1) to a single return series.

    Returns model parameters (α, β, ω), the in-sample conditional volatility
    series (daily, annualised by √252), and a horizon-day-ahead forecast of
    annualised volatility.
    """
    # arch expects returns in percent for numerical stability; multiplying by
    # 100 then dividing the fitted vol by 100 keeps the parameters in their
    # usual ranges. Fit silently — arch prints to stdout by default.
    series = returns.dropna() * 100.0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        am = arch_model(series, vol="GARCH", p=1, q=1, mean="Zero", dist="normal")
        res = am.fit(disp="off")

    omega = float(res.params.get("omega", 0.0))
    alpha = float(res.params.get("alpha[1]", 0.0))
    beta = float(res.params.get("beta[1]", 0.0))

    # Conditional daily vol back to fractional scale (÷100) then annualise.
    cond_daily = res.conditional_volatility / 100.0
    cond_annual = cond_daily * np.sqrt(TRADING_DAYS)

    # Forecast horizon-day-ahead variance, take square root → daily vol.
    fc = res.forecast(horizon=horizon, reindex=False)
    var_path = fc.variance.values[-1] / (100.0 ** 2)
    daily_vol_path = np.sqrt(var_path)
    annual_forecast = float(daily_vol_path.mean() * np.sqrt(TRADING_DAYS))

    persistent = (alpha + beta) > PERSISTENCE_THRESHOLD

    return {
        "alpha": alpha,
        "beta": beta,
        "omega": omega,
        "persistent": persistent,
        "forecast_annual_vol": annual_forecast,
        "daily_vol_path": [float(x) for x in daily_vol_path],
        "conditional_daily_vol": cond_daily,  # pandas Series
    }


def portfolio_garch_vol_forecast(
    returns_df: pd.DataFrame,
    weights: np.ndarray | list[float],
    horizon: int = 30,
) -> dict[str, Any]:
    """Per-asset GARCH + portfolio-level combination via the static correlation matrix.

    Output:
      - historical_vol: realised annualised portfolio vol over the fitted window
      - forecast_vol: horizon-day-ahead GARCH-implied annualised portfolio vol
      - forecast_band_low / high: ±1σ band on the forecast
      - history: list of {date, realised, garch} for plotting
      - forward: list of {day, forecast, low, high}
      - assets: per-asset parameter list
      - persistent_assets: tickers where α+β > 0.95
    """
    w = np.asarray(weights, dtype=float)
    tickers = list(returns_df.columns)
    n = len(tickers)

    # Asset-level fits
    fits: list[dict[str, Any]] = []
    cond_vols = pd.DataFrame(index=returns_df.index)
    forecast_paths = np.zeros((n, horizon))
    persistent_assets: list[str] = []
    for i, ticker in enumerate(tickers):
        try:
            fit = fit_garch(returns_df[ticker], horizon=horizon)
        except Exception as exc:  # noqa: BLE001
            logger.warning("GARCH fit failed for %s: %s", ticker, exc)
            # Fallback: use realised vol as both conditional and forecast.
            std = float(returns_df[ticker].std(ddof=1))
            fits.append({
                "ticker": ticker, "alpha": 0.0, "beta": 0.0, "omega": 0.0,
                "persistent": False, "forecast_annual_vol": std * np.sqrt(TRADING_DAYS),
            })
            forecast_paths[i] = np.full(horizon, std)
            cond_vols[ticker] = std
            continue
        forecast_paths[i] = fit["daily_vol_path"]
        cond_vols[ticker] = fit["conditional_daily_vol"]
        fits.append({
            "ticker": ticker,
            "alpha": fit["alpha"],
            "beta": fit["beta"],
            "omega": fit["omega"],
            "persistent": fit["persistent"],
            "forecast_annual_vol": fit["forecast_annual_vol"],
        })
        if fit["persistent"]:
            persistent_assets.append(ticker)

    # Static correlation across realised returns (more stable than time-varying).
    corr = returns_df.corr().values

    # Portfolio daily vol time series via diag(σ_t) C diag(σ_t).
    aligned = cond_vols[tickers].fillna(method="ffill").fillna(method="bfill").fillna(0.0)
    port_daily_vol = np.empty(len(aligned))
    sigma_vals = aligned.values
    for t in range(len(aligned)):
        s = sigma_vals[t]
        cov_t = np.outer(s, s) * corr
        var_t = float(w @ cov_t @ w)
        port_daily_vol[t] = np.sqrt(max(var_t, 0.0))

    port_annual_vol_series = port_daily_vol * np.sqrt(TRADING_DAYS)

    # Realised portfolio vol over a rolling 21-day window for visual comparison.
    port_daily_returns = returns_df.values @ w
    realised_roll = (
        pd.Series(port_daily_returns, index=returns_df.index)
        .rolling(21)
        .std(ddof=1)
        * np.sqrt(TRADING_DAYS)
    )
    realised_full = float(np.std(port_daily_returns, ddof=1) * np.sqrt(TRADING_DAYS))

    # Forecast portfolio vol from per-asset forecast paths.
    forecast_port_daily = np.empty(horizon)
    for d in range(horizon):
        s = forecast_paths[:, d]
        cov_t = np.outer(s, s) * corr
        forecast_port_daily[d] = np.sqrt(max(float(w @ cov_t @ w), 0.0))
    forecast_port_annual = forecast_port_daily * np.sqrt(TRADING_DAYS)
    forecast_avg = float(forecast_port_annual.mean())
    # ±1σ band derived from variation across the path itself.
    band_sd = float(forecast_port_annual.std(ddof=0))
    forecast_band_low = max(0.0, forecast_avg - band_sd)
    forecast_band_high = forecast_avg + band_sd

    history = [
        {
            "date": str(idx.date()),
            "realised": float(rv),
            "garch": float(gv),
        }
        for idx, rv, gv in zip(
            returns_df.index,
            realised_roll.values,
            port_annual_vol_series,
        )
        if not (np.isnan(rv) or np.isnan(gv))
    ]
    forward = [
        {
            "day": int(d + 1),
            "forecast": float(forecast_port_annual[d]),
            "low": max(0.0, float(forecast_port_annual[d] - band_sd)),
            "high": float(forecast_port_annual[d] + band_sd),
        }
        for d in range(horizon)
    ]

    return {
        "historical_vol": realised_full,
        "forecast_vol": forecast_avg,
        "forecast_band_low": forecast_band_low,
        "forecast_band_high": forecast_band_high,
        "history": history,
        "forward": forward,
        "assets": fits,
        "persistent_assets": persistent_assets,
    }
