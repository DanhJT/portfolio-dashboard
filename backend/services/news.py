"""Per-ticker news fetching via yfinance.

yfinance returns news in two different shapes depending on version:

Old (<0.2.50 or so):
    {"title": ..., "publisher": ..., "link": ...,
     "providerPublishTime": <unix>, ...}

New (current):
    {"id": ..., "content": {
        "title": ..., "summary": ...,
        "pubDate": "ISO string",
        "provider": {"displayName": ...},
        "canonicalUrl": {"url": ...}, ...}}

We normalise to a single flat shape so the API contract stays stable.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import yfinance as yf

logger = logging.getLogger(__name__)

MAX_PER_TICKER = 5


def _coerce_published(raw: Any) -> str | None:
    """Convert yfinance's various timestamp shapes to an ISO string."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        try:
            return datetime.fromtimestamp(raw, tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(raw, str):
        return raw
    return None


def _normalise(item: dict[str, Any], ticker: str) -> dict[str, Any] | None:
    """Flatten a single yfinance news item into our schema. Returns None if unusable."""
    # New nested shape.
    content = item.get("content") if isinstance(item.get("content"), dict) else None
    if content:
        title = content.get("title")
        if not title:
            return None
        provider = content.get("provider") or {}
        canonical = content.get("canonicalUrl") or content.get("clickThroughUrl") or {}
        url = canonical.get("url") if isinstance(canonical, dict) else None
        return {
            "ticker": ticker,
            "title": title,
            "publisher": provider.get("displayName")
            if isinstance(provider, dict)
            else None,
            "url": url,
            "published_at": _coerce_published(content.get("pubDate")),
            "summary": content.get("summary"),
        }

    # Old flat shape.
    title = item.get("title")
    if not title:
        return None
    return {
        "ticker": ticker,
        "title": title,
        "publisher": item.get("publisher"),
        "url": item.get("link"),
        "published_at": _coerce_published(item.get("providerPublishTime")),
        "summary": item.get("summary"),
    }


def _fetch_for_ticker(ticker: str) -> list[dict[str, Any]]:
    """Synchronous yfinance call. Runs in a worker thread to keep the route async."""
    try:
        raw = yf.Ticker(ticker).news or []
    except Exception as exc:  # noqa: BLE001 — yfinance raises a variety of network errors
        logger.warning("news fetch failed for %s: %s", ticker, exc)
        return []
    items: list[dict[str, Any]] = []
    for r in raw[:MAX_PER_TICKER]:
        if not isinstance(r, dict):
            continue
        norm = _normalise(r, ticker)
        if norm:
            items.append(norm)
    return items


async def fetch_news(tickers: list[str]) -> list[dict[str, Any]]:
    """Fetch news for each ticker in parallel and merge into one chronological list.

    Returns flat list of normalised news dicts, newest first. Tickers whose
    fetch fails or returns no news are silently skipped.
    """
    if not tickers:
        return []

    results = await asyncio.gather(
        *(asyncio.to_thread(_fetch_for_ticker, t) for t in tickers),
        return_exceptions=False,
    )
    merged: list[dict[str, Any]] = []
    for chunk in results:
        merged.extend(chunk)

    # Sort newest first; items without a timestamp sink to the bottom.
    def _sort_key(item: dict[str, Any]) -> str:
        return item.get("published_at") or ""

    merged.sort(key=_sort_key, reverse=True)
    return merged
