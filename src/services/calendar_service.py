"""Google Calendar API service — Stage 6.

Idempotency guarantee
---------------------
The ``idempotency_key`` (a UUID stored in the ``events`` table) is normalised
to lowercase hex (hyphens removed) and sent as the Google Calendar event ``id``
field.  Google Calendar treats a supplied ``id`` as a client-assigned
identifier: if an event with that ``id`` already exists in the calendar, the
API returns it unchanged instead of creating a duplicate.

This means tenacity can retry ``create_event`` on any transient failure without
risk of producing duplicate calendar entries — the key and the deduplication
live together in the API call itself.

Retry policy
------------
Three attempts, exponential back-off (1 s → 2 s → 4 s, capped at 10 s).
Retried exceptions:
  * HttpError with status 429 (quota), 500 (server error), 503 (unavailable)
  * Network-level errors: TimeoutError, ConnectionError, OSError
"""

import asyncio
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from src.exceptions import GoogleApiError
from src.schemas.parsed_message import ParsedEvent

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------

_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 503})


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, HttpError):
        return int(exc.resp.status) in _RETRYABLE_STATUS_CODES
    return isinstance(exc, (TimeoutError, ConnectionError, OSError))


_retry = retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_idempotency_key(key: str) -> str:
    """Return a valid Google Calendar event ID derived from *key*.

    Google requires: lowercase alphanumeric only, 5–1024 chars.
    A UUID stripped of hyphens is 32 lowercase hex chars — perfectly valid.
    """
    normalized = re.sub(r"[^a-z0-9]", "", key.lower())
    if len(normalized) < 5:
        normalized = normalized.ljust(5, "0")
    return normalized[:1024]


def _build_service(access_token: str) -> Any:
    credentials = Credentials(token=access_token)
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def _dt_iso(dt: datetime) -> str:
    """Return RFC 3339 string; naïve datetimes are treated as UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


# ---------------------------------------------------------------------------
# Sync primitives (wrapped by tenacity; called via asyncio.to_thread)
# ---------------------------------------------------------------------------


@_retry
def _sync_create_event(
    access_token: str,
    calendar_id: str,
    event_body: dict[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = (
        _build_service(access_token)
        .events()
        .insert(calendarId=calendar_id, body=event_body)
        .execute()
    )
    return result


@_retry
def _sync_list_upcoming(
    access_token: str,
    calendar_id: str,
    count: int,
    time_min: str,
) -> dict[str, Any]:
    result: dict[str, Any] = (
        _build_service(access_token)
        .events()
        .list(
            calendarId=calendar_id,
            timeMin=time_min,
            maxResults=count,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    return result


@_retry
def _sync_delete_event(
    access_token: str,
    calendar_id: str,
    event_id: str,
) -> None:
    _build_service(access_token).events().delete(
        calendarId=calendar_id, eventId=event_id
    ).execute()


@_retry
def _sync_check_conflicts(
    access_token: str,
    calendar_id: str,
    time_min: str,
    time_max: str,
) -> dict[str, Any]:
    result: dict[str, Any] = (
        _build_service(access_token)
        .events()
        .list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
        )
        .execute()
    )
    return result


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------


async def create_event(
    access_token: str,
    calendar_id: str,
    event_data: ParsedEvent,
    idempotency_key: str,
) -> str:
    """Create a Google Calendar event and return the Google event ID.

    ``idempotency_key`` (UUID from the ``events`` table) is normalised and
    sent as the event ``id``.  Retrying with the same key is safe: Google
    returns the existing event instead of creating a duplicate.
    """
    google_event_id = _normalize_idempotency_key(idempotency_key)
    end_at = event_data.end_at or (event_data.start_at + timedelta(hours=1))
    event_body: dict[str, Any] = {
        "id": google_event_id,
        "summary": event_data.title,
        "start": {"dateTime": _dt_iso(event_data.start_at)},
        "end": {"dateTime": _dt_iso(end_at)},
    }
    log = logger.bind(google_event_id=google_event_id, calendar_id=calendar_id)
    try:
        result = await asyncio.to_thread(
            _sync_create_event, access_token, calendar_id, event_body
        )
    except HttpError as exc:
        log.error("calendar_create_failed", status=int(exc.resp.status))
        raise GoogleApiError(
            f"Google API error {exc.resp.status} on create_event"
        ) from exc
    log.info("calendar_event_created")
    return str(result["id"])


async def list_upcoming(
    access_token: str,
    calendar_id: str,
    count: int = 5,
) -> list[dict[str, Any]]:
    """Return up to *count* upcoming events, ordered by start time."""
    time_min = _dt_iso(datetime.now(UTC))
    try:
        result = await asyncio.to_thread(
            _sync_list_upcoming, access_token, calendar_id, count, time_min
        )
    except HttpError as exc:
        raise GoogleApiError(
            f"Google API error {exc.resp.status} on list_upcoming"
        ) from exc
    return list(result.get("items", []))


async def delete_event(
    access_token: str,
    calendar_id: str,
    event_id: str,
) -> bool:
    """Delete a calendar event.  Returns False if the event was not found."""
    try:
        await asyncio.to_thread(_sync_delete_event, access_token, calendar_id, event_id)
    except HttpError as exc:
        if int(exc.resp.status) == 404:
            return False
        raise GoogleApiError(
            f"Google API error {exc.resp.status} on delete_event"
        ) from exc
    return True


async def check_conflicts(
    access_token: str,
    calendar_id: str,
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    """Return events that overlap the [start, end) window."""
    try:
        result = await asyncio.to_thread(
            _sync_check_conflicts,
            access_token,
            calendar_id,
            _dt_iso(start),
            _dt_iso(end),
        )
    except HttpError as exc:
        raise GoogleApiError(
            f"Google API error {exc.resp.status} on check_conflicts"
        ) from exc
    return list(result.get("items", []))
