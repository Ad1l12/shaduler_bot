"""Scheduled task: retry confirmed events that have not been synced yet.

Runs every 60 seconds.  Finds all events in status='confirmed' that were
created more than 60 seconds ago (they should have been synced immediately
after confirmation but weren't — process crash, transient API error, etc.)
and attempts to sync each one.

Session isolation
-----------------
Each event gets two independent sessions/transactions:

  1. Sync session  — runs sync_event(); committed on success; rolled back on
                     any exception.  _mark_failed inside sync_event flushes
                     into THIS session, so a rollback undoes it.

  2. Failure session — opened only when the sync session raised.  Writes
                       status='failed' and increments retry_count in a
                       separate committed transaction that is NOT rolled back.
                       After this commit the event has status='failed' and
                       will no longer be selected by get_pending_for_retry
                       (which filters for status='confirmed'), so the event
                       cannot loop indefinitely.
"""

import structlog

from src.db.repositories.event_repo import EventRepository
from src.db.session import AsyncSessionFactory
from src.services.event_service import EventService

logger = structlog.get_logger(__name__)


async def retry_pending_events() -> None:
    """Entry point called by APScheduler every 60 seconds."""
    async with AsyncSessionFactory() as session:
        event_service = EventService(session)
        events = await event_service.get_pending_events_for_retry()

    if not events:
        return

    logger.info("retry_pending_start", count=len(events))

    for event in events:
        # ── attempt sync in its own session ──────────────────────────────
        try:
            async with AsyncSessionFactory() as session:
                event_service = EventService(session)
                await event_service.sync_event(event.id)
                await session.commit()
            logger.info("retry_pending_synced", event_id=event.id)

        except Exception as exc:
            # The sync session was rolled back (or never committed).
            # _mark_failed's flush was part of that session, so it was
            # rolled back too.  Persist the failure in a fresh session.
            error_msg = str(exc)
            logger.warning("retry_pending_failed", event_id=event.id, error=error_msg)

            try:
                async with AsyncSessionFactory() as fail_session:
                    repo = EventRepository(fail_session)
                    await repo.update_status(event.id, "failed", last_error=error_msg)
                    await repo.increment_retry(event.id, error_msg)
                    await fail_session.commit()
            except Exception as db_exc:
                # Last resort: if we can't even write the failure, log and
                # move on.  The event stays 'confirmed' and will be retried
                # next cycle, but at least the scheduler keeps running.
                logger.error(
                    "retry_mark_failed_error",
                    event_id=event.id,
                    error=str(db_exc),
                )
