"""Point-in-time inputs for the value signal: book equity and shares outstanding.

Book-to-market at a past rebalance date must use only what was public then, so
the backtest can't use today's price-to-book. Instead:

- Book equity comes from SEC EDGAR's XBRL "frames" API: one request returns
  every filer's balance-sheet value for one calendar quarter. A quarter's figure
  is treated as known only REPORTING_LAG after the quarter ends (10-Qs are due
  within 40-45 days and 10-Ks within 60-90 days for large filers).
- Shares outstanding come from Yahoo's share-count history. Those counts are
  as-reported (not split-adjusted), so they are put on today's split basis and
  multiplied by split-adjusted closes to get market equity.

SEC requires a contact email in the User-Agent. Set SEC_CONTACT_EMAIL (or a full
SEC_USER_AGENT) in the repo-root .env locally and as a GitHub Actions secret.
Everything is cached under backend/.cache so repeat runs are fast.
"""
from __future__ import annotations

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent
CACHE_DIR = _BACKEND_DIR / ".cache"
FRAMES_CACHE_DIR = CACHE_DIR / "sec_frames"
SHARES_CACHE_PATH = CACHE_DIR / "shares_history.json"

FRAMES_URL = "https://data.sec.gov/api/xbrl/frames/{concept}/USD/{period}.json"
# Parent-company equity first; the NCI-inclusive total fills filers that only tag that.
EQUITY_CONCEPTS = (
    "us-gaap/StockholdersEquity",
    "us-gaap/StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
)
REPORTING_LAG = timedelta(days=90)
# Ignore book values older than this at a rebalance (company stopped filing / data gap).
MAX_BOOK_AGE = timedelta(days=460)
# Quarters that ended this long ago are final, so their cached frames never expire.
FRAME_FINAL_AFTER = timedelta(days=300)
FRAME_CACHE_TTL = timedelta(days=7)
SEC_PAUSE_S = 0.15  # SEC allows 10 requests/second

SHARES_CACHE_TTL = timedelta(days=7)
SHARES_WORKERS = 8
# A share count more than this far from its neighbours is a data glitch
# (typically a split recorded on the wrong date), not a real change.
SHARES_GLITCH_RATIO = 1.4


# ---------------------------------------------------------------------------
# SEC access
# ---------------------------------------------------------------------------

def _load_dotenv() -> None:
    """Read KEY=VALUE lines from the repo-root .env without overriding the environment."""
    path = _REPO_ROOT / ".env"
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def sec_user_agent() -> str | None:
    """User-Agent for SEC requests, or None if no contact is configured."""
    _load_dotenv()
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if ua:
        return ua
    email = os.environ.get("SEC_CONTACT_EMAIL", "").strip()
    return f"portfolio-dashboard research {email}" if email else None


def _quarter_periods(start: date, end: date) -> list[tuple[str, date]]:
    """(frame period, quarter-end date) for every calendar quarter ending in [start, end]."""
    out: list[tuple[str, date]] = []
    year, q = start.year, (start.month - 1) // 3 + 1
    while True:
        month = q * 3
        q_end = (pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0)).date()
        if q_end > end:
            break
        if q_end >= start:
            out.append((f"CY{year}Q{q}I", q_end))
        q += 1
        if q == 5:
            year, q = year + 1, 1
    return out


def _fetch_frame(concept: str, period: str, q_end: date, ua: str) -> list[dict]:
    """One frame's rows, from the disk cache when it is still valid."""
    FRAMES_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = FRAMES_CACHE_DIR / f"{concept.replace('/', '_')}_{period}.json"
    if path.exists():
        final = date.today() - q_end > FRAME_FINAL_AFTER
        fresh = time.time() - path.stat().st_mtime < FRAME_CACHE_TTL.total_seconds()
        if final or fresh:
            try:
                return json.loads(path.read_text())
            except ValueError:
                pass

    url = FRAMES_URL.format(concept=concept, period=period)
    rows: list[dict] | None = None
    for attempt in range(1, 4):
        try:
            resp = requests.get(url, headers={"User-Agent": ua}, timeout=30)
            time.sleep(SEC_PAUSE_S)
            if resp.status_code == 404:  # quarter not published yet
                rows = []
                break
            resp.raise_for_status()
            rows = [
                {"cik": r["cik"], "end": r["end"], "val": r["val"]}
                for r in resp.json().get("data", [])
            ]
            break
        except Exception as exc:  # noqa: BLE001 — network errors come in many shapes
            if attempt == 3:
                raise RuntimeError(f"SEC frame {concept} {period} failed: {exc}") from exc
            time.sleep(2.0 * attempt)
    path.write_text(json.dumps(rows))
    return rows or []


def load_book_equity(ciks: set[int], start: date, end: date) -> pd.DataFrame:
    """Quarterly book equity for `ciks` as a long frame: cik, end, available, val.

    `available` is the first date the figure may be used (quarter end + lag).
    """
    ua = sec_user_agent()
    if not ua:
        raise RuntimeError(
            "SEC contact not configured: set SEC_CONTACT_EMAIL in .env "
            "(or as a GitHub Actions secret) to enable the value signal"
        )
    records: dict[tuple[int, str], float] = {}
    periods = _quarter_periods(start, end)
    for concept in EQUITY_CONCEPTS:
        for period, q_end in periods:
            for row in _fetch_frame(concept, period, q_end, ua):
                key = (int(row["cik"]), row["end"])
                if key[0] in ciks and key not in records:
                    records[key] = float(row["val"])
    if not records:
        return pd.DataFrame(columns=["cik", "end", "available", "val"])
    df = pd.DataFrame(
        [(cik, end_, val) for (cik, end_), val in records.items()],
        columns=["cik", "end", "val"],
    )
    df["end"] = pd.to_datetime(df["end"])
    df["available"] = df["end"] + REPORTING_LAG
    logger.info("book equity: %d quarterly values across %d companies (%d quarters)",
                len(df), df["cik"].nunique(), len(periods))
    return df.sort_values(["cik", "end"]).reset_index(drop=True)


def book_equity_asof(book: pd.DataFrame, when: pd.Timestamp) -> pd.Series:
    """Latest usable book equity per CIK at `when` (NaN-free; stale values dropped)."""
    if book.empty:
        return pd.Series(dtype=float)
    usable = book[(book["available"] <= when) & (book["end"] >= when - MAX_BOOK_AGE)]
    if usable.empty:
        return pd.Series(dtype=float)
    return usable.groupby("cik")["val"].last()


# ---------------------------------------------------------------------------
# Shares outstanding
# ---------------------------------------------------------------------------

def _fetch_shares(ticker: str, start: str) -> tuple[str, pd.Series | None]:
    try:
        raw = yf.Ticker(ticker).get_shares_full(start=start)
    except Exception as exc:  # noqa: BLE001
        logger.debug("shares history failed for %s: %s", ticker, exc)
        return ticker, None
    if raw is None or len(raw) == 0:
        return ticker, None
    s = pd.Series(raw.values, index=pd.to_datetime(raw.index).tz_localize(None), dtype=float)
    s = s[~s.index.duplicated(keep="last")].sort_index()
    s = s[s > 0]
    # Month-end sampling is plenty for a monthly strategy and keeps the cache small.
    s = s.resample("ME").last().dropna()
    return ticker, s if len(s) else None


def load_shares_history(tickers: list[str], start: date) -> dict[str, pd.Series]:
    """As-reported shares outstanding per ticker (month-end), cached for a week."""
    start_s = start.isoformat()
    cached: dict[str, pd.Series] = {}
    try:
        blob = json.loads(SHARES_CACHE_PATH.read_text())
        saved = datetime.fromisoformat(blob["saved_at"])
        if (datetime.now(timezone.utc) - saved < SHARES_CACHE_TTL
                and blob.get("start", "9999") <= start_s):
            for t, pairs in blob["data"].items():
                idx = pd.to_datetime([p[0] for p in pairs])
                cached[t] = pd.Series([p[1] for p in pairs], index=idx, dtype=float)
    except Exception:  # noqa: BLE001 — missing/corrupt cache just means refetch
        cached = {}

    todo = [t for t in tickers if t not in cached]
    if todo:
        logger.info("shares history: %d cached, fetching %d", len(cached), len(todo))
        with ThreadPoolExecutor(max_workers=SHARES_WORKERS) as pool:
            for ticker, series in pool.map(lambda t: _fetch_shares(t, start_s), todo):
                if series is not None:
                    cached[ticker] = series
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            SHARES_CACHE_PATH.write_text(json.dumps({
                "saved_at": datetime.now(timezone.utc).isoformat(),
                "start": start_s,
                "data": {
                    t: [[d.strftime("%Y-%m-%d"), float(v)] for d, v in s.items()]
                    for t, s in cached.items()
                },
            }))
        except OSError as exc:
            logger.debug("could not write shares cache: %s", exc)
    return {t: cached[t] for t in tickers if t in cached}


def split_adjusted_shares(
    shares: dict[str, pd.Series], splits: pd.DataFrame, index: pd.DatetimeIndex
) -> pd.DataFrame:
    """Daily shares outstanding on today's split basis, aligned to `index`.

    Each as-reported count is multiplied by every split that happened after
    its date. Counts that disagree with their neighbours by more than
    SHARES_GLITCH_RATIO (a split booked on the wrong date) are dropped.
    """
    cols: dict[str, pd.Series] = {}
    for ticker, s in shares.items():
        if ticker in splits.columns:
            ratios = splits[ticker].replace(0.0, np.nan).dropna()
            ratios = ratios[ratios > 0]
        else:
            ratios = pd.Series(dtype=float)
        if len(ratios):
            # factor(d) = product of split ratios strictly after d
            after = np.array([float(ratios[ratios.index > d].prod()) for d in s.index])
            adj = s * after
        else:
            adj = s.copy()
        med = adj.rolling(5, center=True, min_periods=1).median()
        ok = (adj / med).between(1 / SHARES_GLITCH_RATIO, SHARES_GLITCH_RATIO)
        adj = adj[ok]
        if adj.empty:
            continue
        cols[ticker] = adj.reindex(adj.index.union(index)).ffill().reindex(index)
    return pd.DataFrame(cols, index=index)
