"""Module-aware portfolio commentary generator.

Kept under the historical ``claude_client`` filename. The implementation is
local and rule-based — no external API calls — but the output is shaped per
module to mirror the system-prompt focus areas defined in the spec:

  * overview       — overall portfolio risk profile (default)
  * optimization   — MVO reallocation deltas and Sharpe improvement
  * black_litterman — view impact vs equilibrium prior
  * risk           — Monte Carlo VaR + worst stress scenario + GARCH regime
  * liquidity      — concentration vs ADV, Kelly divergence, rebalancing cost
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

MODEL = "rule-based-v2"


class CommentaryError(RuntimeError):
    """Raised when commentary generation fails."""


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def _pct(x: float | None, digits: int = 2) -> str:
    if x is None:
        return "n/a"
    return f"{x * 100:.{digits}f}%"


def _num(x: float | None, digits: int = 2) -> str:
    if x is None:
        return "n/a"
    return f"{x:.{digits}f}"


def _sharpe_band(s: float) -> str:
    if s >= 1.5:
        return "excellent risk-adjusted performance"
    if s >= 1.0:
        return "strong risk-adjusted performance"
    if s >= 0.5:
        return "modest risk-adjusted performance"
    if s >= 0.0:
        return "weak risk-adjusted performance"
    return "negative risk-adjusted performance"


def _vol_band(v: float) -> str:
    if v < 0.15:
        return "low"
    if v < 0.25:
        return "moderate"
    if v < 0.40:
        return "elevated"
    return "high"


# ---------------------------------------------------------------------------
# Module: overview (legacy / default)
# ---------------------------------------------------------------------------

def _overview(m: dict[str, Any]) -> str:
    ret = m.get("annualised_return", 0.0)
    vol = m.get("annualised_volatility", 0.0)
    sharpe = m.get("sharpe_ratio", 0.0)
    var = m.get("var_95", 0.0)
    cvar = m.get("cvar_95", 0.0)
    dd = m.get("max_drawdown", 0.0)
    holdings = m.get("holdings", []) or []
    top = max(holdings, key=lambda h: h.get("weight", 0.0), default=None)
    contrib = max(
        holdings, key=lambda h: h.get("volatility_contribution", 0.0), default=None
    )

    sentences = [
        f"The portfolio returned {_pct(ret)} annualised against {_pct(vol)} "
        f"volatility (Sharpe {_num(sharpe)}) — {_sharpe_band(sharpe)} at a "
        f"{_vol_band(vol)} risk level."
    ]
    if top and contrib:
        sentences.append(
            f"{top['ticker']} carries the largest weight at "
            f"{_pct(top['weight'], 1)}; {contrib['ticker']} dominates risk "
            f"contribution at {_pct(contrib['volatility_contribution'], 1)}."
        )
    sentences.append(
        f"On a typical bad day expect losses near {_pct(var)} (95% VaR), with "
        f"the worst 5% averaging {_pct(cvar)} (CVaR) and peak-to-trough "
        f"drawdown over the period of {_pct(dd)}."
    )
    if contrib and contrib.get("volatility_contribution", 0.0) >= 0.35:
        sentences.append(
            f"Action: trim or hedge {contrib['ticker']} — it is the single "
            "biggest driver of portfolio risk."
        )
    else:
        sentences.append(
            "Action: profile looks balanced; monitor correlation drift around "
            "the next earnings cycle."
        )
    return " ".join(sentences)


# ---------------------------------------------------------------------------
# Module: optimization
# ---------------------------------------------------------------------------

def _optimization(m: dict[str, Any]) -> str:
    cur = m.get("current") or {}
    ms = m.get("max_sharpe") or {}
    mv = m.get("min_vol") or {}

    cur_w = dict(zip(cur.get("tickers", []), cur.get("weights", [])))
    ms_w = dict(zip(ms.get("tickers", []), ms.get("weights", [])))

    deltas = [
        (t, ms_w.get(t, 0.0) - cur_w.get(t, 0.0))
        for t in set(cur_w) | set(ms_w)
    ]
    deltas.sort(key=lambda x: abs(x[1]), reverse=True)
    biggest = deltas[:2]

    parts: list[str] = []
    if cur and ms:
        d_sharpe = ms.get("sharpe", 0.0) - cur.get("sharpe", 0.0)
        parts.append(
            f"Mean-variance optimisation lifts Sharpe from {_num(cur.get('sharpe'))} "
            f"to {_num(ms.get('sharpe'))} (Δ {_num(d_sharpe, 2)}), "
            f"with return {_pct(ms.get('return'))} at "
            f"{_pct(ms.get('volatility'))} volatility."
        )
    if biggest:
        rebal = ", ".join(
            f"{'+' if d > 0 else ''}{_pct(d, 1)} {t}" for t, d in biggest
        )
        parts.append(
            f"Largest reallocations from the current book to the Max-Sharpe "
            f"point: {rebal}."
        )
    if mv:
        parts.append(
            f"Minimum-variance alternative sits at {_pct(mv.get('volatility'))} vol "
            f"and {_pct(mv.get('return'))} return — useful if drawdown control "
            f"matters more than return capture."
        )
    parts.append(
        "Trade-off: optimised allocations capture historical regimes well but "
        "are notoriously sensitive to estimation error in mean returns — size "
        "any rotation conservatively."
    )
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Module: Black-Litterman
# ---------------------------------------------------------------------------

def _black_litterman(m: dict[str, Any]) -> str:
    prior = m.get("prior_weights") or {}
    post = m.get("posterior_weights") or {}
    views = m.get("views") or []

    deltas = [(t, post.get(t, 0.0) - prior.get(t, 0.0)) for t in set(prior) | set(post)]
    deltas.sort(key=lambda x: abs(x[1]), reverse=True)
    biggest = deltas[:2]

    parts: list[str] = []
    if views:
        parts.append(
            f"You expressed {len(views)} view"
            f"{'s' if len(views) != 1 else ''}; the posterior tilts the "
            f"market-equilibrium prior accordingly while keeping every "
            f"selected name in the book."
        )
    if biggest:
        tilts = ", ".join(
            f"{'+' if d > 0 else ''}{_pct(d, 1)} {t}" for t, d in biggest
        )
        parts.append(f"Largest tilts vs prior: {tilts}.")
    parts.append(
        "Read the size of those tilts as the strength of your conviction "
        "blended with the market's: higher confidence on a view pushes the "
        "posterior further from equilibrium, but never past what your "
        "covariance estimate allows."
    )
    if not views:
        parts.append(
            "No views supplied → posterior matches the prior (market portfolio). "
            "Add a view in the table to tilt the book."
        )
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Module: risk
# ---------------------------------------------------------------------------

def _risk(m: dict[str, Any]) -> str:
    mc = m.get("monte_carlo") or {}
    stress = m.get("stress_tests") or []
    garch = m.get("garch") or {}

    parts: list[str] = []
    if mc:
        parts.append(
            f"Monte Carlo (10k paths, 1Y horizon): 95% VaR {_pct(mc.get('var_95'))}, "
            f"99% VaR {_pct(mc.get('var_99'))}, CVaR 95% {_pct(mc.get('cvar_95'))}. "
            f"Probability of >20% loss: {_pct(mc.get('p_loss_20'))}."
        )
    if stress:
        worst = min(stress, key=lambda s: s.get("portfolio_return") or 0.0)
        parts.append(
            f"Worst historical replay is {worst.get('name', '?')} "
            f"({_pct(worst.get('portfolio_return'))} return, "
            f"max drawdown {_pct(worst.get('max_drawdown'))}, "
            f"worst day {_pct(worst.get('worst_day'))})."
        )
    if garch:
        persistent = garch.get("persistent_assets") or []
        fwd = garch.get("forecast_vol")
        hist = garch.get("historical_vol")
        if fwd is not None and hist is not None:
            delta = fwd - hist
            direction = "rising" if delta > 0 else "falling"
            parts.append(
                f"GARCH(1,1) 30-day forecast vol is {_pct(fwd)} vs realised "
                f"{_pct(hist)} — vol regime {direction}."
            )
        if persistent:
            parts.append(
                f"Persistence alarm: {', '.join(persistent)} have α+β > 0.95, "
                f"meaning shocks decay slowly — drawdowns there will compound "
                f"longer than a Gaussian model would imply."
            )
    if not parts:
        parts.append("Insufficient risk data to summarise.")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Module: liquidity
# ---------------------------------------------------------------------------

def _liquidity(m: dict[str, Any]) -> str:
    rows = m.get("positions") or []
    aum = m.get("aum") or 0.0
    if not rows:
        return "No liquidity data available."

    worst = max(rows, key=lambda r: r.get("pct_of_adv", 0.0))
    longest = max(rows, key=lambda r: r.get("days_to_liquidate_20", 0.0))
    kelly_off = [
        r for r in rows
        if abs((r.get("kelly_weight") or 0.0) - (r.get("current_weight") or 0.0)) > 0.10
    ]

    parts: list[str] = [
        f"AUM ${aum:,.0f} across {len(rows)} positions. The most concentrated "
        f"trade is {worst.get('ticker')} at {_pct(worst.get('pct_of_adv'), 1)} "
        f"of 30-day ADV."
    ]
    parts.append(
        f"At a 20% participation rate, the slowest unwind would be "
        f"{longest.get('ticker')} at {_num(longest.get('days_to_liquidate_20'), 1)} "
        "trading days — manageable but worth keeping in mind for any rapid de-risk."
    )
    if kelly_off:
        names = ", ".join(r["ticker"] for r in kelly_off[:3])
        parts.append(
            f"Kelly divergence > 10pp on {names}: current sizing is materially "
            "out of step with Kelly — review whether that reflects intentional "
            "risk budgeting or stale weights."
        )
    else:
        parts.append("Current sizing tracks Kelly recommendations closely.")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_MODULE_GENERATORS = {
    "overview": _overview,
    "optimization": _optimization,
    "black_litterman": _black_litterman,
    "risk": _risk,
    "liquidity": _liquidity,
}


async def generate_commentary(
    metrics: dict[str, Any],
    module: str = "overview",
) -> tuple[str, str]:
    """Generate module-specific commentary. Returns (text, iso_timestamp)."""
    gen = _MODULE_GENERATORS.get(module)
    if gen is None:
        raise CommentaryError(f"unknown commentary module: {module}")
    try:
        text = gen(metrics)
    except Exception as exc:  # noqa: BLE001 — surface as 502 with context
        raise CommentaryError(f"failed to generate {module} commentary: {exc}") from exc
    if not text.strip():
        raise CommentaryError(f"{module} commentary was empty")
    return text.strip(), datetime.now(timezone.utc).isoformat()
