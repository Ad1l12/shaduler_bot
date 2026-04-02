"""APScheduler setup.

Exposes a single ``scheduler`` instance and a ``create_scheduler()`` factory
used by the FastAPI lifespan.  The scheduler runs inside the same event loop
as FastAPI — no separate process or thread is needed.

Jobs:
  retry_pending_events   — every 60 seconds
  refresh_expiring_tokens — every 30 minutes
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.tasks.refresh_tokens import refresh_expiring_tokens
from src.tasks.retry_pending import retry_pending_events


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        retry_pending_events,
        trigger=IntervalTrigger(seconds=60),
        id="retry_pending_events",
        replace_existing=True,
        max_instances=1,  # prevent overlap if a run takes longer than 60 s
    )

    scheduler.add_job(
        refresh_expiring_tokens,
        trigger=IntervalTrigger(minutes=30),
        id="refresh_expiring_tokens",
        replace_existing=True,
        max_instances=1,
    )

    return scheduler
