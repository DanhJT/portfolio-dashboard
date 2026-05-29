"""APScheduler glue for monthly value-momentum rebalancing.

The cron trigger fires every weekday at 09:30 America/New_York between the
1st and 7th of the month. The job itself then checks whether *today* is the
first US trading day of the month (skipping weekends and federal holidays)
and only runs the strategy on that day.

Two-step filter (cron + in-job check) keeps the schedule explicit and
robust: we never re-run on an off day, even if the host's clock jumps or
the process restarts mid-month.
"""
from __future__ import annotations

import logging
from datetime import date

import holidays
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from services.strategy import run_value_momentum_strategy

logger = logging.getLogger(__name__)

TZ = "America/New_York"

_US_HOLIDAYS = holidays.country_holidays("US")


def _is_first_trading_day_of_month(d: date) -> bool:
    """True iff d is a weekday, not a US federal holiday, and no earlier day this month is."""
    if d.weekday() >= 5 or d in _US_HOLIDAYS:
        return False
    for day in range(1, d.day):
        earlier = d.replace(day=day)
        if earlier.weekday() < 5 and earlier not in _US_HOLIDAYS:
            return False
    return True


def _rebalance(app) -> None:
    """Scheduler callback. Re-runs strategy and updates app.state.portfolio."""
    # APScheduler already restricts firing to 09:30 ET on day 1-7 (Mon-Fri),
    # so we just need to confirm this is the *first* trading day of the month.
    today_date = date.today()
    if not _is_first_trading_day_of_month(today_date):
        logger.debug("scheduler tick on %s — not the first trading day; skipping", today_date)
        return

    portfolio = run_value_momentum_strategy()
    app.state.portfolio = portfolio
    logger.info(
        "Rebalanced: %s → %s | weights: %s",
        today_date.isoformat(),
        portfolio["tickers"],
        [round(w, 4) for w in portfolio["weights"]],
    )


def start_scheduler(app) -> BackgroundScheduler:
    """Start the background scheduler and register the monthly rebalance job."""
    scheduler = BackgroundScheduler(timezone=TZ)
    trigger = CronTrigger(
        day="1-7",
        day_of_week="mon-fri",
        hour=9,
        minute=30,
        timezone=TZ,
    )
    scheduler.add_job(
        lambda: _rebalance(app),
        trigger=trigger,
        id="value_momentum_rebalance",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info("scheduler started; rebalance fires 09:30 %s on first trading day of each month", TZ)
    return scheduler
