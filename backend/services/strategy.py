"""Live value-momentum strategy following Asness, Moskowitz & Pedersen (2013).

Universe
--------
All current S&P 500 constituents, read from ``backend/data/sp500_constituents.csv``
(refresh it with ``backend/scripts/update_sp500.py``). The committed file makes
each run reproducible and keeps Wikipedia out of the request path.

Signals
-------
- Momentum (Jegadeesh & Titman 1993): 12-1 price momentum. Total return from
  t-12 months to t-2 months — i.e. skip the most recent month so we don't
  pick up the one-month reversal effect.
- Value (Fama & French 1992): book-to-market = 1 / price-to-book.
- Composite: equal-weighted z-scores, each winsorised at ±3σ.

Portfolio construction
----------------------
- Multiple share classes of one company (GOOGL/GOOG, FOX/FOXA) collapse to the
  single highest-scoring line, so the portfolio never doubles up on one issuer.
- Top 15 names by composite score.
- Score-weighted: shift so the lowest selected score becomes 0, normalise to
  sum to 1.0, then iteratively cap each weight at 35% and redistribute the
  excess proportionally to the uncapped names.
- If anything goes wrong (network, missing data, degenerate signals), fall
  back to an equal-weighted basket of five large-cap defaults.

Scale notes
-----------
Ranking ~500 names rather than 50 makes both signals network-heavy, so:
prices download in chunks with retries, price-to-book is fetched with modest
concurrency and cached on disk for a week, and a coverage guard fails the run
(into the fallback) rather than silently ranking a shrunken universe.
"""
from __future__ import annotations

import csv
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent.parent
CONSTITUENTS_PATH = _BACKEND_DIR / "data" / "sp500_constituents.csv"
PB_CACHE_PATH = _BACKEND_DIR / ".cache" / "pb_cache.json"
PB_CACHE_TTL = timedelta(days=7)

# Used only if the constituents CSV is missing — the old hand-picked universe.
FALLBACK_UNIVERSE: list[str] = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "LLY", "JPM", "V", "UNH",
    "XOM", "MA", "JNJ", "PG", "HD", "AVGO", "COST", "MRK", "CVX", "ABBV",
    "WMT", "BAC", "CRM", "KO", "PEP", "ACN", "MCD", "TMO", "CSCO", "ABT",
    "ADBE", "NFLX", "WFC", "TXN", "DHR", "LIN", "PM", "AMD", "AMGN", "NEE",
    "RTX", "LOW", "INTU", "CAT", "SPGI", "ISRG", "GS", "BLK", "AMAT", "SYK",
]

TOP_N = 15
WEIGHT_CAP = 0.35
WINSOR_LIMIT = 3.0

# Equal-weight fallback basket: five large-cap names across distinct sectors,
# used when live signals can't be computed (e.g. data provider rate-limits us).
FALLBACK_TICKERS: list[str] = ["AAPL", "MSFT", "JPM", "JNJ", "XOM"]
TRADING_DAYS_PER_MONTH = 21
MOMENTUM_LOOKBACK_DAYS = 12 * TRADING_DAYS_PER_MONTH   # ~252
MOMENTUM_SKIP_DAYS = TRADING_DAYS_PER_MONTH            # ~21

# Yahoo throttles large bursts, so prices come down in chunks and P/B fetches
# stay at modest concurrency.
DOWNLOAD_CHUNK = 100
DOWNLOAD_ATTEMPTS = 3
VALUE_WORKERS = 4
VALUE_ATTEMPTS = 2
# Below this share of the universe we'd be ranking a biased subset, so fail
# into the fallback instead of publishing a half-screened portfolio.
MIN_MOMENTUM_COVERAGE = 0.80


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


def _download_closes(tickers: list[str], period: str = "14mo") -> pd.DataFrame:
    """Daily closes for many tickers, downloaded in retried chunks.

    A chunk that fails every attempt is logged and skipped; the caller's
    coverage guard decides whether what's left is still representative.
    """
    frames: list[pd.DataFrame] = []
    for start in range(0, len(tickers), DOWNLOAD_CHUNK):
        chunk = tickers[start:start + DOWNLOAD_CHUNK]
        for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
            try:
                raw = yf.download(
                    tickers=chunk,
                    period=period,
                    interval="1d",
                    auto_adjust=True,
                    progress=False,
                    threads=True,
                    group_by="column",
                )
                if raw.empty:
                    raise RuntimeError("empty frame")
                close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
                if not isinstance(close, pd.DataFrame):
                    close = close.to_frame()
                if len(chunk) == 1:
                    close.columns = chunk
                frames.append(close)
                break
            except Exception as exc:  # noqa: BLE001 — network errors come in many shapes
                if attempt < DOWNLOAD_ATTEMPTS:
                    delay = 3.0 * (2 ** (attempt - 1))
                    logger.warning(
                        "price chunk %d-%d failed (attempt %d/%d): %s — retrying in %.0fs",
                        start, start + len(chunk), attempt, DOWNLOAD_ATTEMPTS, exc, delay,
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        "price chunk %d-%d failed after %d attempts: %s — skipping",
                        start, start + len(chunk), DOWNLOAD_ATTEMPTS, exc,
                    )

    if not frames:
        raise RuntimeError("yfinance returned no price data for any chunk")
    combined = pd.concat(frames, axis=1)
    # Chunk boundaries can leave duplicate columns if a ticker repeats.
    return combined.loc[:, ~combined.columns.duplicated()]


def _momentum_signal(tickers: list[str]) -> pd.Series:
    """12-1 price momentum z-score for each ticker. NaN for tickers missing data."""
    close = _download_closes(list(tickers))

    # 12-1 return: price ~21 trading days ago divided by price ~252 trading days ago.
    if len(close) < MOMENTUM_LOOKBACK_DAYS + 1:
        raise RuntimeError(
            f"only {len(close)} daily bars available; need {MOMENTUM_LOOKBACK_DAYS + 1}"
        )
    end = close.iloc[-MOMENTUM_SKIP_DAYS]
    start = close.iloc[-MOMENTUM_LOOKBACK_DAYS]
    # Names listed for less than the full lookback (recent index additions,
    # spin-offs) have NaN at one end and drop out here.
    momentum = (end / start - 1.0).replace([np.inf, -np.inf], np.nan).dropna()
    return _zscore_winsorise(momentum)


def _load_pb_cache() -> dict[str, float]:
    """Price-to-book values cached on disk, if still within the TTL."""
    try:
        blob = json.loads(PB_CACHE_PATH.read_text())
        saved_at = datetime.fromisoformat(blob["saved_at"])
        if datetime.now(timezone.utc) - saved_at > PB_CACHE_TTL:
            logger.info("price-to-book cache is stale — refetching")
            return {}
        cached = blob.get("price_to_book") or {}
        return {k: float(v) for k, v in cached.items() if isinstance(v, (int, float)) and v > 0}
    except Exception:  # noqa: BLE001 — missing/corrupt cache is not an error
        return {}


def _save_pb_cache(pb_map: dict[str, float]) -> None:
    try:
        PB_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        PB_CACHE_PATH.write_text(json.dumps({
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "price_to_book": pb_map,
        }))
    except OSError as exc:
        logger.debug("could not write price-to-book cache: %s", exc)


def _fetch_price_to_book(ticker: str) -> tuple[str, float | None]:
    """One ticker's P/B from yfinance Ticker.info, retried. None on failure."""
    for attempt in range(1, VALUE_ATTEMPTS + 1):
        try:
            info = yf.Ticker(ticker).info or {}
        except Exception as exc:  # noqa: BLE001 — network errors come in many shapes
            if attempt < VALUE_ATTEMPTS:
                time.sleep(1.0 * attempt)
                continue
            logger.debug("value fetch failed for %s: %s", ticker, exc)
            return ticker, None
        pb = info.get("priceToBook")
        # A negative or zero P/B means negative book equity — not a value
        # signal we can rank, so treat it as missing rather than retrying.
        if pb is None or not isinstance(pb, (int, float)) or pb <= 0:
            return ticker, None
        return ticker, float(pb)
    return ticker, None


def _value_signal(tickers: list[str]) -> pd.Series:
    """Book-to-market z-score for each ticker. Drops missing/negative P/B."""
    cached = _load_pb_cache()
    pb_map: dict[str, float] = {t: cached[t] for t in tickers if t in cached}
    todo = [t for t in tickers if t not in pb_map]
    if pb_map:
        logger.info("price-to-book: %d from cache, %d to fetch", len(pb_map), len(todo))

    # yfinance Ticker.info is network-bound; parallelise so we don't wait
    # minutes, but stay modest so Yahoo doesn't throttle a 500-name sweep.
    if todo:
        with ThreadPoolExecutor(max_workers=VALUE_WORKERS) as pool:
            futures = [pool.submit(_fetch_price_to_book, t) for t in todo]
            for fut in as_completed(futures):
                ticker, pb = fut.result()
                if pb is not None:
                    pb_map[ticker] = pb
        _save_pb_cache(pb_map)

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
        if cik is None:
            continue
        if cik in best:
            logger.debug("dropping %s: same issuer as higher-scoring %s", ticker, best[cik])
        else:
            best[cik] = ticker
    keep = [t for t in composite.index if cik_by_ticker.get(t) is None or best.get(cik_by_ticker[t]) == t]
    dropped = len(composite) - len(keep)
    if dropped:
        logger.info("dropped %d duplicate share-class line(s)", dropped)
    return composite.loc[keep]


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
        universe_t, cik_by_ticker = load_universe()
        universe = list(universe_t)
        logger.info("screening %d-name universe (as of %s)", len(universe),
                    universe_as_of() or "unknown")

        mom = _momentum_signal(universe)
        coverage = len(mom) / len(universe) if universe else 0.0
        if coverage < MIN_MOMENTUM_COVERAGE or len(mom) < TOP_N:
            raise RuntimeError(
                f"momentum covered {len(mom)}/{len(universe)} names "
                f"({coverage:.0%} < {MIN_MOMENTUM_COVERAGE:.0%} required)"
            )

        val = _value_signal(universe)
        common = mom.index.intersection(val.index)
        logger.info(
            "signal coverage — universe:%d momentum:%d value:%d overlap:%d",
            len(universe), len(mom), len(val), len(common),
        )
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

        composite = _dedupe_share_classes(composite, cik_by_ticker)
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
