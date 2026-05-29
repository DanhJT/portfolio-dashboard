"""Monte Carlo VaR via Cholesky-correlated normal returns."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

INITIAL_VALUE = 100.0


def simulate_portfolio_paths(
    returns_df: pd.DataFrame,
    weights: np.ndarray | list[float],
    n_simulations: int = 10000,
    horizon_days: int = 252,
    seed: int = 11,
) -> dict[str, Any]:
    """Simulate ``n_simulations`` correlated daily-return paths.

    Returns a dict with VaR/CVaR, probability of loss, and percentile paths
    (5/25/50/75/95) over the simulation horizon.
    """
    rng = np.random.default_rng(seed)
    mu = returns_df.mean().values
    cov = returns_df.cov().values
    n_assets = len(mu)
    w = np.asarray(weights, dtype=float)

    # Cholesky for correlated shocks. Add tiny ridge for numerical safety.
    try:
        L = np.linalg.cholesky(cov + 1e-12 * np.eye(n_assets))
    except np.linalg.LinAlgError:
        # Fall back to eigen-based square root if cov isn't PSD due to FP drift.
        evals, evecs = np.linalg.eigh(cov)
        evals = np.clip(evals, 0.0, None)
        L = evecs @ np.diag(np.sqrt(evals))

    # Pre-allocate path matrix: rows = simulations, cols = days+1.
    paths = np.empty((n_simulations, horizon_days + 1), dtype=float)
    paths[:, 0] = INITIAL_VALUE

    # Vectorised: draw daily standardised normals then map to correlated daily
    # returns. Loop along the time axis since each step compounds.
    for d in range(1, horizon_days + 1):
        z = rng.standard_normal((n_simulations, n_assets))
        daily = mu + z @ L.T  # shape (n_simulations, n_assets)
        port_daily = daily @ w  # shape (n_simulations,)
        paths[:, d] = paths[:, d - 1] * (1.0 + port_daily)

    terminal = paths[:, -1]
    terminal_return = terminal / INITIAL_VALUE - 1.0

    var_95 = float(-np.quantile(terminal_return, 0.05))
    var_99 = float(-np.quantile(terminal_return, 0.01))
    cvar_95 = float(-terminal_return[terminal_return <= np.quantile(terminal_return, 0.05)].mean())
    cvar_99 = float(-terminal_return[terminal_return <= np.quantile(terminal_return, 0.01)].mean())

    percentiles = {
        "p05": np.quantile(paths, 0.05, axis=0),
        "p25": np.quantile(paths, 0.25, axis=0),
        "p50": np.quantile(paths, 0.50, axis=0),
        "p75": np.quantile(paths, 0.75, axis=0),
        "p95": np.quantile(paths, 0.95, axis=0),
    }

    return {
        "var_95": var_95,
        "var_99": var_99,
        "cvar_95": cvar_95,
        "cvar_99": cvar_99,
        "p_loss_10": float((terminal_return < -0.10).mean()),
        "p_loss_20": float((terminal_return < -0.20).mean()),
        "p_loss_30": float((terminal_return < -0.30).mean()),
        "percentile_paths": {
            k: [float(x) for x in v] for k, v in percentiles.items()
        },
        "horizon_days": horizon_days,
        "n_simulations": n_simulations,
    }
