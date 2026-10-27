"""Value-momentum strategy (Asness, Moskowitz & Pedersen 2013) and its backtest.

One engine produces both the monthly backtest and the live portfolio: every
rebalance, past or present, runs the same rules on the data that was available
the day before it. The live holdings are simply the latest rebalance.

Universe
--------
Current S&P 500 constituents, read from ``backend/data/sp500_constituents.csv``
(refresh it with ``backend/scripts/update_sp500.py``). At each past rebalance a
stock is eligible only if it had already joined the index, so later additions
(often recent big winners) can't leak backwards. Companies that have since
left the index are missing, which leaves some survivorship bias.

Signals (computed from data up to the close before each rebalance)
-------------------------------------------------------------------
- Momentum (Jegadeesh & Titman 1993): total return from ~12 months to ~1
  month ago, skipping the latest month to avoid the one-month reversal.
- Value (Fama & French 1992): book-to-market. Book equity is the latest
  quarterly SEC filing at least 90 days old; market equity is shares
  outstanding x price (see services/fundamentals.py).
- Composite: equal-weighted z-scores, each winsorised at +/-3 sigma.

Portfolio construction
----------------------
- Multiple share classes of one company (GOOGL/GOOG, FOX/FOXA) collapse to the
  single highest-scoring line.
- Hold the top 10% of companies by composite score (about 50 names).
- Weight in proportion to composite score, then cap any single name at 35%
  and spread the excess across the rest.
- Rebalance on the first US trading day of each month; between rebalances the
  weights drift with prices.
- If value data is too sparse at a rebalance, rank on momentum alone.
"""
from __future__ import annotations

import csv
import logging
import math
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

from services import fundamentals

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent.parent
CONSTITUENTS_PATH = _BACKEND_DIR / "data" / "sp500_constituents.csv"

# Used only if the constituents CSV is missing — the old hand-picked universe.
FALLBACK_UNIVERSE: list[str] = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "LLY", "JPM", "V", "UNH",
    "XOM", "MA", "JNJ", "PG", "HD", "AVGO", "COST", "MRK", "CVX", "ABBV",
    "WMT", "BAC", "CRM", "KO", "PEP", "ACN", "MCD", "TMO", "CSCO", "ABT",
    "ADBE", "NFLX", "WFC", "TXN", "DHR", "LIN", "PM", "AMD", "AMGN", "NEE",
    "RTX", "LOW", "INTU", "CAT", "SPGI", "ISRG", "GS", "BLK", "AMAT", "SYK",
]

SELECTION_PCT = 0.10      # hold the top 10% of ranked companies
MIN_HOLDINGS = 10         # never fewer than this, however small the ranked set
WEIGHT_CAP = 0.35
WINSOR_LIMIT = 3.0
BENCHMARK = "SPY"

# Equal-weight fallback basket: five large-cap names across distinct sectors,
# used when live signals can't be computed (e.g. data provider rate-limits us).
FALLBACK_TICKERS: list[str] = ["AAPL", "MSFT", "JPM", "JNJ", "XOM"]
TRADING_DAYS_PER_MONTH = 21
MOMENTUM_LOOKBACK_DAYS = 12 * TRADING_DAYS_PER_MONTH   # ~252
MOMENTUM_SKIP_DAYS = TRADING_DAYS_PER_MONTH            # ~21

BACKTEST_YEARS = 5
# Price history needed before the first backtest rebalance (momentum lookback + slack).
HISTORY_BUFFER = timedelta(days=430)

# Yahoo throttles large bursts, so prices come down in retried chunks.
DOWNLOAD_CHUNK = 100
DOWNLOAD_ATTEMPTS = 3
# Below this share of the universe we'd be ranking a biased subset, so the
# rebalance is skipped (backtest) or fails into the fallback (live).
MIN_MOMENTUM_COVERAGE = 0.80
# Use the value signal only if it covers at least this share of the momentum names.
MIN_VALUE_OVERLAP = 0.50


# ---------------------------------------------------------------------------
# Universe
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def load_universe() -> tuple[tuple[str, ...], dict[str, str]]:
    """Read the constituents CSV. Returns (tickers, ticker -> CIK).

    Falls back to the legacy 50-name list if the file is missing, so a fresh
    checkout without the data file still produces a portfolio.
    """
    if not CONSTITUENTS_PATH.exists():
        logger.warning(
            "%s missing — falling back to the legacy %d-name universe; "
            "run backend/scripts/update_sp500.py to restore the S&P 500 list",
            CONSTITUENTS_PATH, len(FALLBACK_UNIVERSE),
        )
        return tuple(FALLBACK_UNIVERSE), {}

    tickers: list[str] = []
    cik_by_ticker: dict[str, str] = {}
    with CONSTITUENTS_PATH.open() as fh:
        # The first line is an `# as_of: …` provenance comment.
        rows = csv.DictReader(line for line in fh if not line.startswith("#"))
        for row in rows:
            symbol = (row.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            tickers.append(symbol)
            cik = (row.get("cik") or "").strip()
            if cik and cik.strip("0"):
                cik_by_ticker[symbol] = cik

    if not tickers:
        logger.warning("%s parsed to zero tickers — using legacy universe", CONSTITUENTS_PATH)
        return tuple(FALLBACK_UNIVERSE), {}
    return tuple(tickers), cik_by_ticker


@lru_cache(maxsize=1)
def load_date_added() -> dict[str, pd.Timestamp]:
    """ticker -> date it joined the S&P 500 (tickers with no date are omitted)."""
    out: dict[str, pd.Timestamp] = {}
    try:
        with CONSTITUENTS_PATH.open() as fh:
            for row in csv.DictReader(line for line in fh if not line.startswith("#")):
                added = (row.get("date_added") or "").strip()
                if added:
                    out[(row.get("symbol") or "").strip().upper()] = pd.Timestamp(added)
    except OSError:
        pass
    return out


def eligible_at(universe: list[str], when: pd.Timestamp) -> list[str]:
    """Members of `universe` that had joined the index by `when`."""
    added = load_date_added()
    return [t for t in universe if added.get(t, pd.Timestamp.min) <= when]


def universe_as_of() -> str | None:
    """The as-of date recorded in the constituents CSV header, if present."""
    try:
        with CONSTITUENTS_PATH.open() as fh:
            first = fh.readline()
    except OSError:
        return None
    marker = "as_of:"
    if marker not in first:
        return None
    return first.split(marker, 1)[1].split("—")[0].strip() or None


# ---------------------------------------------------------------------------
# Market data
# ---------------------------------------------------------------------------

@dataclass
class MarketData:
    adj_close: pd.DataFrame   # total-return prices (dividends + splits)
    close: pd.DataFrame       # split-adjusted only, for market equity
    splits: pd.DataFrame      # split ratio on each split date, else 0


def _field(raw: pd.DataFrame, name: str, chunk: list[str]) -> pd.DataFrame:
    if isinstance(raw.columns, pd.MultiIndex):
        out = raw[name].copy()
    else:
        out = raw[[name]].copy()
        out.columns = chunk
    return out


def _download_chunk(chunk: list[str], start: date) -> dict[str, pd.DataFrame]:
    """One yfinance call. Returns the fields for tickers that actually came back."""
    raw = yf.download(
        tickers=chunk,
        start=start.isoformat(),
        interval="1d",
        auto_adjust=False,
        actions=True,
        progress=False,
        threads=True,
        group_by="column",
    )
    if raw.empty:
        return {}
    adj = _field(raw, "Adj Close", chunk)
    # yfinance reports a failed ticker as an all-NaN column rather than raising.
    got = [t for t in adj.columns if adj[t].notna().any()]
    out = {"adj": adj[got], "close": _field(raw, "Close", chunk)[got]}
    if "Stock Splits" in raw.columns.get_level_values(0):
        out["splits"] = _field(raw, "Stock Splits", chunk).reindex(columns=got)
    return out


def download_market_data(tickers: list[str], start: date) -> MarketData:
    """Daily prices and splits for many tickers.

    Yahoo throttles big bursts and then returns empty columns for some
    tickers without raising, so every ticker is checked and the missing ones
    are retried in slower passes. Whatever is still missing after that is
    left to the coverage guard.
    """
    adj, close, splits = [], [], []
    pending = list(dict.fromkeys(tickers))
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 2):
        if attempt > 1:
            delay = 10.0 * (attempt - 1)
            logger.warning("retrying %d tickers Yahoo didn't return (pass %d) in %.0fs: %s",
                           len(pending), attempt, delay, pending[:10])
            time.sleep(delay)
        chunk_size = DOWNLOAD_CHUNK if attempt == 1 else max(10, DOWNLOAD_CHUNK // (2 * attempt))
        missing: list[str] = []
        for i in range(0, len(pending), chunk_size):
            chunk = pending[i:i + chunk_size]
            try:
                part = _download_chunk(chunk, start)
            except Exception as exc:  # noqa: BLE001 — network errors come in many shapes
                logger.warning("price chunk failed: %s", exc)
                part = {}
            got = set(part["adj"].columns) if part else set()
            if part:
                adj.append(part["adj"])
                close.append(part["close"])
                if "splits" in part:
                    splits.append(part["splits"])
            missing += [t for t in chunk if t not in got]
            time.sleep(1.0)  # be gentle between chunks
        pending = missing
        if not pending:
            break
    if pending:
        logger.error("no price data for %d tickers after retries: %s", len(pending), pending)
    if not adj:
        raise RuntimeError("yfinance returned no price data")

    def _combine(frames: list[pd.DataFrame]) -> pd.DataFrame:
        if not frames:
            return pd.DataFrame()
        df = pd.concat(frames, axis=1)
        df = df.loc[:, ~df.columns.duplicated()]
        df.index = pd.to_datetime(df.index).tz_localize(None)
        return df.sort_index()

    adj_df = _combine(adj)
    # Drop rows where nearly everything is missing (holiday stubs, partial days).
    adj_df = adj_df[adj_df.notna().mean(axis=1) > 0.5]
    close_df = _combine(close).reindex(index=adj_df.index, columns=adj_df.columns)
    splits_df = _combine(splits).reindex(index=adj_df.index).fillna(0.0)
    return MarketData(adj_close=adj_df, close=close_df, splits=splits_df)


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

def _zscore_winsorise(series: pd.Series) -> pd.Series:
    """Cross-sectional z-score clipped to ±WINSOR_LIMIT."""
    s = series.replace([np.inf, -np.inf], np.nan).dropna()
    if len(s) < 2:
        return pd.Series(dtype=float)
    std = s.std(ddof=1)
    if std == 0 or np.isnan(std):
        return pd.Series(0.0, index=s.index)
    z = (s - s.mean()) / std
    return z.clip(-WINSOR_LIMIT, WINSOR_LIMIT)


def momentum_signal(adj_close: pd.DataFrame, upto: int) -> pd.Series:
    """12-1 momentum z-scores using rows [0, upto) — i.e. data before row `upto`."""
    if upto < MOMENTUM_LOOKBACK_DAYS:
        return pd.Series(dtype=float)
    end = adj_close.iloc[upto - MOMENTUM_SKIP_DAYS]
    start = adj_close.iloc[upto - MOMENTUM_LOOKBACK_DAYS]
    # Names listed for less than the full lookback have NaN at one end and drop out.
    return _zscore_winsorise(end / start - 1.0)


def value_signal(
    book: pd.DataFrame,
    shares: pd.DataFrame,
    close: pd.DataFrame,
    cik_by_ticker: dict[str, str],
    upto: int,
) -> pd.Series:
    """Book-to-market z-scores as known on the day before row `upto`."""
    if book.empty or shares.empty or upto < 1:
        return pd.Series(dtype=float)
    when = close.index[upto - 1]
    be_by_cik = fundamentals.book_equity_asof(book, when)
    price = close.iloc[upto - 1]
    sh = shares.iloc[upto - 1]
    btm: dict[str, float] = {}
    for ticker, cik in cik_by_ticker.items():
        be = be_by_cik.get(int(cik))
        me = price.get(ticker, np.nan) * sh.get(ticker, np.nan)
        # Negative book equity has no meaningful value ranking; skip it.
        if be is None or not np.isfinite(me) or me <= 0 or be <= 0:
            continue
        btm[ticker] = be / me
    return _zscore_winsorise(pd.Series(btm, dtype=float))


# ---------------------------------------------------------------------------
# Portfolio construction
# ---------------------------------------------------------------------------

def _dedupe_share_classes(composite: pd.Series, cik_by_ticker: dict[str, str]) -> pd.Series:
    """Keep only the highest-scoring share class per issuer (by CIK).

    GOOGL/GOOG, FOX/FOXA and NWS/NWSA are each one company in the index, so
    holding both lines would double the intended issuer exposure.
    """
    if not cik_by_ticker:
        return composite
    best: dict[str, str] = {}
    for ticker in composite.sort_values(ascending=False).index:
        cik = cik_by_ticker.get(ticker)
        if cik is not None and cik not in best:
            best[cik] = ticker
    keep = [t for t in composite.index if cik_by_ticker.get(t) is None or best.get(cik_by_ticker[t]) == t]
    return composite.loc[keep]


def _apply_weight_cap(weights: pd.Series, cap: float) -> pd.Series:
    """Iteratively cap each weight and spread the excess across uncapped names."""
    w = weights.astype(float).copy()
    for _ in range(50):
        over = w > cap + 1e-9
        if not over.any():
            break
        excess = float((w[over] - cap).sum())
        w[over] = cap
        under = w < cap - 1e-9
        under_sum = float(w[under].sum())
        if under_sum <= 0 or excess <= 0:
            break
        w[under] = w[under] + excess * (w[under] / under_sum)
    # Final renormalise to wash out any floating-point drift.
    total = float(w.sum())
    if total > 0:
        w = w / total
    return w


def holdings_count(n_ranked: int) -> int:
    """How many names the top-percentile rule selects from `n_ranked` companies."""
    return min(n_ranked, max(MIN_HOLDINGS, math.ceil(SELECTION_PCT * n_ranked)))


def construct_weights(composite: pd.Series) -> pd.Series:
    """Top 10% by composite score, weighted in proportion to score, capped at 35%.

    Selected scores sit in the top decile of a z-score blend, so they are
    normally all positive and weights are simply score / sum(scores). If any
    selected score is not positive (tiny or degenerate universe), scores are
    shifted so the lowest still gets a small positive weight.
    """
    n = holdings_count(len(composite))
    top = composite.nlargest(n).astype(float)
    if top.min() > 0:
        raw = top
    else:
        spread = float(top.max() - top.min())
        raw = (top - top.min()) + (spread / n if spread > 0 else 1.0)
    weights = raw / raw.sum()
    return _apply_weight_cap(weights, WEIGHT_CAP).sort_values(ascending=False)


# ---------------------------------------------------------------------------
# Backtest engine
# ---------------------------------------------------------------------------

@dataclass
class Rebalance:
    date: pd.Timestamp
    strategy: str
    weights: pd.Series
    ranked: int            # companies with a composite score
    value_coverage: float  # share of momentum names that also had a value score
    turnover: float = 0.0  # one-way: sum(|new - drifted old|) / 2


@dataclass
class StrategyRun:
    returns: pd.Series           # daily portfolio returns over the backtest
    benchmark: pd.Series         # daily SPY returns, same dates
    rebalances: list[Rebalance]
    adj_close: pd.DataFrame      # universe prices, for holdings diagnostics
    pending: bool = False        # latest rebalance is today, before its first close
    notes: list[str] = field(default_factory=list)

    @property
    def latest(self) -> Rebalance:
        return self.rebalances[-1]


def _rebalance_rows(index: pd.DatetimeIndex, first_allowed: pd.Timestamp) -> list[int]:
    """Row numbers of the first trading day of each month on or after `first_allowed`."""
    months = pd.Series(range(len(index)), index=index).groupby([index.year, index.month]).first()
    return [int(r) for r in months.values
            if r >= MOMENTUM_LOOKBACK_DAYS and index[r] >= first_allowed]


def _select(
    md: MarketData, book: pd.DataFrame, shares: pd.DataFrame,
    universe: list[str], cik_by_ticker: dict[str, str], upto: int, when: pd.Timestamp,
) -> Rebalance | None:
    """Run the ranking rules on data before row `upto`. None if coverage is too thin."""
    universe = eligible_at(universe, when)
    mom = momentum_signal(md.adj_close[universe], upto)
    coverage = len(mom) / len(universe)
    if coverage < MIN_MOMENTUM_COVERAGE:
        logger.warning("%s: momentum covers %d/%d names (%.0f%%) — skipping rebalance",
                       when.date(), len(mom), len(universe), coverage * 100)
        return None
    members = set(universe)
    eligible_ciks = {t: c for t, c in cik_by_ticker.items() if t in members}
    val = value_signal(book, shares, md.close, eligible_ciks, upto)
    common = mom.index.intersection(val.index)
    value_cov = len(common) / len(mom) if len(mom) else 0.0
    if value_cov >= MIN_VALUE_OVERLAP:
        composite = 0.5 * mom.loc[common] + 0.5 * val.loc[common]
        strategy = "value-momentum"
    else:
        composite = mom
        strategy = "momentum"
    composite = _dedupe_share_classes(composite, cik_by_ticker)
    return Rebalance(
        date=when, strategy=strategy, weights=construct_weights(composite),
        ranked=len(composite), value_coverage=value_cov,
    )


def run_strategy(today: date | None = None) -> StrategyRun:
    """Backtest the rules over the last BACKTEST_YEARS and return the full run.

    Raises if market data can't be loaded; the caller decides how to degrade.
    """
    from scheduler import _is_first_trading_day_of_month

    today = today or date.today()
    universe_t, cik_by_ticker = load_universe()
    universe = list(universe_t)
    first_rebalance = pd.Timestamp(today) - pd.DateOffset(years=BACKTEST_YEARS)
    start = (first_rebalance - HISTORY_BUFFER).date()
    logger.info("backtest: %d-name universe (as of %s), prices from %s",
                len(universe), universe_as_of() or "unknown", start)

    md = download_market_data([BENCHMARK] + universe, start)
    if BENCHMARK not in md.adj_close.columns:
        raise RuntimeError(f"benchmark {BENCHMARK} missing from price data")
    universe = [t for t in universe if t in md.adj_close.columns]
    index = md.adj_close.index

    notes: list[str] = []
    try:
        ciks = {int(c) for c in cik_by_ticker.values()}
        book = fundamentals.load_book_equity(
            ciks, start - timedelta(days=550), today)
        raw_shares = fundamentals.load_shares_history(universe, start - timedelta(days=60))
        shares = fundamentals.split_adjusted_shares(raw_shares, md.splits, index)
        logger.info("value inputs: book equity for %d companies, shares for %d tickers",
                    book["cik"].nunique() if not book.empty else 0, shares.shape[1])
    except Exception as exc:  # noqa: BLE001
        logger.error("value inputs unavailable (%s) — ranking on momentum only", exc)
        notes.append(f"value data unavailable: {exc}")
        book, shares = pd.DataFrame(), pd.DataFrame()

    rows = _rebalance_rows(index, first_rebalance)
    # Before today's close, the first trading day of a new month isn't in the
    # price index yet; rebalance on the data we have so live holdings switch on time.
    pending = bool(
        _is_first_trading_day_of_month(today)
        and index[-1].date() < today
        and (not rows or index[rows[-1]].month != today.month)
    )
    if not rows and not pending:
        raise RuntimeError("not enough price history for a single rebalance")

    rets = md.adj_close[universe].pct_change(fill_method=None)
    bench = md.adj_close[BENCHMARK].pct_change(fill_method=None)

    rebalances: list[Rebalance] = []
    daily: dict[pd.Timestamp, float] = {}
    held: pd.Series | None = None  # drifted weights
    row_set = set(rows)
    start_row = rows[0] if rows else len(index)
    for r in range(start_row, len(index)):
        if r in row_set:
            rb = _select(md, book, shares, universe, cik_by_ticker, r, index[r])
            if rb is not None:
                if held is not None:
                    both = rb.weights.index.union(held.index)
                    rb.turnover = float(
                        (rb.weights.reindex(both, fill_value=0) - held.reindex(both, fill_value=0)).abs().sum() / 2)
                else:
                    rb.turnover = 1.0
                rebalances.append(rb)
                held = rb.weights.copy()
        if held is None:
            continue
        day = rets.iloc[r].reindex(held.index).fillna(0.0)
        port = float((held * day).sum())
        daily[index[r]] = port
        grown = held * (1.0 + day)
        held = grown / grown.sum()

    if pending:
        rb = _select(md, book, shares, universe, cik_by_ticker, len(index), pd.Timestamp(today))
        if rb is not None:
            if held is not None:
                both = rb.weights.index.union(held.index)
                rb.turnover = float(
                    (rb.weights.reindex(both, fill_value=0) - held.reindex(both, fill_value=0)).abs().sum() / 2)
            rebalances.append(rb)
        else:
            pending = False

    if not rebalances:
        raise RuntimeError("no rebalance had enough data coverage")

    port_rets = pd.Series(daily, name="portfolio").sort_index()
    bench_rets = bench.reindex(port_rets.index).fillna(0.0).rename("benchmark")
    latest = rebalances[-1]
    logger.info(
        "backtest: %d rebalances %s → %s, latest %s holds %d names (%s), top weight %.2f%%",
        len(rebalances), rebalances[0].date.date(), latest.date.date(), latest.date.date(),
        len(latest.weights), latest.strategy, latest.weights.max() * 100,
    )
    return StrategyRun(
        returns=port_rets, benchmark=bench_rets, rebalances=rebalances,
        adj_close=md.adj_close, pending=pending, notes=notes,
    )


# ---------------------------------------------------------------------------
# Public entrypoints
# ---------------------------------------------------------------------------

def portfolio_from_run(run: StrategyRun) -> dict[str, Any]:
    """The live holdings (latest rebalance) in the ActivePortfolio shape."""
    latest = run.latest
    rebalanced_at = datetime.combine(latest.date.date(), datetime.min.time()).replace(
        tzinfo=timezone.utc).isoformat()
    return {
        "tickers": list(latest.weights.index),
        "weights": [float(w) for w in latest.weights.values],
        "strategy": latest.strategy,
        "rebalanced_at": rebalanced_at,
    }


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
    """Current portfolio for the live API: the latest rebalance of the backtest.

    Falls back to an equal-weight basket if market data can't be loaded, so
    the API never starts without a portfolio.
    """
    try:
        return portfolio_from_run(run_strategy())
    except Exception as exc:  # noqa: BLE001
        logger.error("strategy failed: %s — falling back to equal-weight defaults", exc)
        fb = _equal_weight_fallback()
        fb["rebalanced_at"] = rebalanced_at or datetime.now(timezone.utc).isoformat()
        return fb
