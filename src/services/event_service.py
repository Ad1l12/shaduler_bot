"""Event Service — Stage 7: orchestration.

Connects the parser output → DB → Google Calendar in three discrete steps:

  1. create_pending_event  — saves ParsedEvent to DB with status='pending'
  2. confirm_event         — user clicked "Create"; moves to status='confirmed'
  3. sync_event            — sends to Google Calendar; moves to 'synced' or 'failed'

Status-transition guarantee for sync_event
-------------------------------------------
Any failure (missing credentials, GoogleApiError, unexpected exception) is
caught before it propagates.  The status is flushed to 'failed' and
retry_count is incremented *before* the exception re-raises.  This means the
caller's commit will persist the 'failed' state, and the event will never be
stuck as 'confirmed' indefinitely.

The retry scheduler (Stage 9) handles events that remain 'confirmed' older
than 60 seconds — this covers the edge case where the process crashes between
confirm and sync.
"""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repositories.event_repo import EventRepository
from src.db.repositories.oauth_credential_repo import OAuthCredentialRepository
from src.exceptions import EventNotFoundError, GoogleApiError, TokenExpiredError
from src.models.event import Event
from src.schemas.parsed_message import ParsedEvent
from src.services import calendar_service
from src.services.auth_service import AuthService

logger = structlog.get_logger(__name__)


class EventService:
    def __init__(self, session: AsyncSession) -> None:
        self._event_repo = EventRepository(session)
        self._oauth_repo = OAuthCredentialRepository(session)
        self._auth = AuthService(session)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_pending_event(self, user_id: int, parsed: ParsedEvent) -> Event:
        """Persist a new event in 'pending' status.

        Called immediately after the parser produces a ParsedEvent, before the
        user has confirmed creation.
        """
        event = await self._event_repo.create(
            user_id=user_id,
            title=parsed.title,
            start_at=parsed.start_at,
            end_at=parsed.end_at,
        )
        logger.info("event_created", event_id=event.id, user_id=user_id)
        return event

    async def confirm_event(self, event_id: int) -> Event:
        """Advance status from 'pending' to 'confirmed' (user tapped Create).

        Raises EventNotFoundError if the event does not exist.
        """
        event = await self._event_repo.update_status(event_id, "confirmed")
        if event is None:
            raise EventNotFoundError(f"Event {event_id} not found")
        logger.info("event_confirmed", event_id=event_id)
        return event

    async def sync_event(self, event_id: int) -> Event:
        """Send a confirmed event to Google Calendar.

        Status transitions (always committed by the caller):
          confirmed → synced   on success
          confirmed → failed   on any error (credentials missing or API failure)

        The 'failed' status is flushed before the exception re-raises, so the
        caller's session.commit() will always persist the correct final state.

        Raises:
            EventNotFoundError   — event does not exist in the database.
            TokenExpiredError    — user has no valid Google credentials.
            GoogleApiError       — Google Calendar API returned an error after
                                   all tenacity retries were exhausted.
        """
        event = await self._event_repo.get_by_id(event_id)
        if event is None:
            raise EventNotFoundError(f"Event {event_id} not found")

        log = logger.bind(event_id=event_id, user_id=event.user_id)

        if event.status != "confirmed":
            log.warning("sync_skipped_wrong_status", status=event.status)
            return event

        # ── resolve credentials ──────────────────────────────────────────
        access_token = await self._auth.get_valid_token(event.user_id)
        if access_token is None:
            err = "No valid Google credentials — user must reconnect via /connect"
            await self._mark_failed(event_id, err)
            log.warning("sync_failed_no_credentials")
            raise TokenExpiredError(err)

        cred_row = await self._oauth_repo.get_by_user_id(event.user_id)
        calendar_id = (
            cred_row.calendar_id
            if cred_row is not None and cred_row.calendar_id
            else "primary"
        )

        # ── call Google Calendar API ─────────────────────────────────────
        parsed = ParsedEvent(
            title=event.title,
            start_at=event.start_at,
            end_at=event.end_at,
        )
        try:
            google_event_id = await calendar_service.create_event(
                access_token=access_token,
                calendar_id=calendar_id,
                event_data=parsed,
                idempotency_key=str(event.idempotency_key),
            )
        except GoogleApiError as exc:
            err = str(exc)
            await self._mark_failed(event_id, err)
            log.error("sync_failed", error=err)
            raise

        # ── success ──────────────────────────────────────────────────────
        synced = await self._event_repo.update_status(
            event_id, "synced", external_id=google_event_id
        )
        log.info("event_synced", google_event_id=google_event_id)
        # update_status returns None only if the event vanishes between the
        # get_by_id above and this call — practically impossible, but guard it.
        assert synced is not None
        return synced

    async def get_pending_events_for_retry(self) -> list[Event]:
        """Return confirmed events older than 60 s (input for the retry scheduler)."""
        return await self._event_repo.get_pending_for_retry(older_than_seconds=60)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _mark_failed(self, event_id: int, error: str) -> None:
        """Set status='failed', increment retry_count, and store the error.

        Both flushes happen inside the caller's transaction, so the caller's
        commit persists both changes atomically.
        """
        await self._event_repo.update_status(event_id, "failed", last_error=error)
        await self._event_repo.increment_retry(event_id, error)
