"""Shared dependency helpers for the new analytical routers."""
from __future__ import annotations

from fastapi import HTTPException, Request


def active_portfolio(request: Request) -> dict:
    """Return the live ``app.state.portfolio`` or 503 if not yet initialised."""
    active = getattr(request.app.state, "portfolio", None)
    if not active or not active.get("tickers") or not active.get("weights"):
        raise HTTPException(503, "active portfolio not initialised yet")
    return active
