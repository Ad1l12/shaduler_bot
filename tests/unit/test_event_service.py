"""Unit tests for EventService — Stage 7.

All external collaborators (repos, AuthService, calendar_service) are mocked
with AsyncMock so no database or network calls are made.

Key invariant verified by this suite
-------------------------------------
sync_event MUST transition status to 'failed' (and flush) before any
exception re-raises.  If this guarantee breaks, events get stuck as
'confirmed' forever and the retry scheduler cannot distinguish them from
legitimately pending events.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.exceptions import EventNotFoundError, GoogleApiError, TokenExpiredError
from src.models.event import Event
from src.models.oauth_credential import OAuthCredential
from src.schemas.parsed_message import ParsedEvent
from src.services.event_service import EventService

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_USER_ID = 42
_EVENT_ID = 7
_IDEMPOTENCY_KEY = uuid.UUID("123e4567-e89b-12d3-a456-426614174000")
_GOOGLE_EVENT_ID = "123e4567e89b12d3a456426614174000"
_ACCESS_TOKEN = "ya29.test-token"
_CALENDAR_ID = "primary"


def _make_parsed() -> ParsedEvent:
    return ParsedEvent(
        title="Team meeting",
        start_at=datetime(2026, 6, 1, 18, 0, tzinfo=UTC),
    )


def _make_event(status: str = "confirmed") -> Event:
    event = MagicMock(spec=Event)
    event.id = _EVENT_ID
    event.user_id = _USER_ID
    event.title = "Team meeting"
    event.start_at = datetime(2026, 6, 1, 18, 0, tzinfo=UTC)
    event.end_at = None
    event.status = status
    event.idempotency_key = _IDEMPOTENCY_KEY
    event.retry_count = 0
    return event


def _make_cred(calendar_id: str = _CALENDAR_ID) -> OAuthCredential:
    cred = MagicMock(spec=OAuthCredential)
    cred.calendar_id = calendar_id
    return cred


def _make_service() -> tuple[EventService, MagicMock, MagicMock, MagicMock, MagicMock]:
    """Return (service, event_repo_mock, oauth_repo_mock, auth_mock, session_mock)."""
    session = MagicMock()

    event_repo = MagicMock()
    event_repo.get_by_id = AsyncMock()
    event_repo.create = AsyncMock()
    event_repo.update_status = AsyncMock()
    event_repo.increment_retry = AsyncMock()
    event_repo.get_pending_for_retry = AsyncMock()

    oauth_repo = MagicMock()
    oauth_repo.get_by_user_id = AsyncMock()

    auth = MagicMock()
    auth.get_valid_token = AsyncMock()

    svc = EventService.__new__(EventService)
    svc._event_repo = event_repo  # type: ignore[attr-defined]
    svc._oauth_repo = oauth_repo  # type: ignore[attr-defined]
    svc._auth = auth  # type: ignore[attr-defined]

    return svc, event_repo, oauth_repo, auth, session


# ---------------------------------------------------------------------------
# create_pending_event
# ---------------------------------------------------------------------------


class TestCreatePendingEvent:
    @pytest.mark.asyncio
    async def test_creates_event_with_parsed_data(self) -> None:
        svc, event_repo, *_ = _make_service()
        created = _make_event(status="pending")
        event_repo.create.return_value = created
        parsed = _make_parsed()

        result = await svc.create_pending_event(_USER_ID, parsed)

        event_repo.create.assert_awaited_once_with(
            user_id=_USER_ID,
            title=parsed.title,
            start_at=parsed.start_at,
            end_at=parsed.end_at,
        )
        assert result is created

    @pytest.mark.asyncio
    async def test_returns_event_from_repo(self) -> None:
        svc, event_repo, *_ = _make_service()
        expected = _make_event(status="pending")
        event_repo.create.return_value = expected
        result = await svc.create_pending_event(_USER_ID, _make_parsed())
        assert result.status == "pending"


# ---------------------------------------------------------------------------
# confirm_event
# ---------------------------------------------------------------------------


class TestConfirmEvent:
    @pytest.mark.asyncio
    async def test_moves_status_to_confirmed(self) -> None:
        svc, event_repo, *_ = _make_service()
        confirmed = _make_event(status="confirmed")
        event_repo.update_status.return_value = confirmed

        result = await svc.confirm_event(_EVENT_ID)

        event_repo.update_status.assert_awaited_once_with(_EVENT_ID, "confirmed")
        assert result is confirmed

    @pytest.mark.asyncio
    async def test_raises_event_not_found_when_missing(self) -> None:
        svc, event_repo, *_ = _make_service()
        event_repo.update_status.return_value = None

        with pytest.raises(EventNotFoundError):
            await svc.confirm_event(_EVENT_ID)


# ---------------------------------------------------------------------------
# sync_event — success path
# ---------------------------------------------------------------------------


class TestSyncEventSuccess:
    @pytest.mark.asyncio
    async def test_happy_path_returns_synced_event(self) -> None:
        svc, event_repo, oauth_repo, auth, _ = _make_service()
        event = _make_event(status="confirmed")
        synced = _make_event(status="synced")
        event_repo.get_by_id.return_value = event
        event_repo.update_status.return_value = synced
        auth.get_valid_token.return_value = _ACCESS_TOKEN
        oauth_repo.get_by_user_id.return_value = _make_cred()

        with patch(
            "src.services.event_service.calendar_service.create_event",
            new=AsyncMock(return_value=_GOOGLE_EVENT_ID),
        ):
            result = await svc.sync_event(_EVENT_ID)

        assert result is synced

    @pytest.mark.asyncio
    async def test_sets_synced_status_and_external_id(self) -> None:
        svc, event_repo, oauth_repo, auth, _ = _make_service()
        event_repo.get_by_id.return_value = _make_event(status="confirmed")
        event_repo.update_status.return_value = _make_event(status="synced")
        auth.get_valid_token.return_value = _ACCESS_TOKEN
        oauth_repo.get_by_user_id.return_value = _make_cred()

        with patch(
            "src.services.event_service.calendar_service.create_event",
            new=AsyncMock(return_value=_GOOGLE_EVENT_ID),
        ):
            await svc.sync_event(_EVENT_ID)

        event_repo.update_status.assert_awaited_once_with(
            _EVENT_ID, "synced", external_id=_GOOGLE_EVENT_ID
        )

    @pytest.mark.asyncio
    async def test_passes_idempotency_key_as_string_to_calendar(self) -> None:
        svc, event_repo, oauth_repo, auth, _ = _make_service()
        event_repo.get_by_id.return_value = _make_event(status="confirmed")
        event_repo.update_status.return_value = _make_event(status="synced")
        auth.get_valid_token.return_value = _ACCESS_TOKEN
        oauth_repo.get_by_user_id.return_value = _make_cred()

        mock_create = AsyncMock(return_value=_GOOGLE_EVENT_ID)
        with patch(
            "src.services.event_service.calendar_service.create_event", new=mock_create
        ):
            await svc.sync_event(_EVENT_ID)

        _, kwargs = mock_create.call_args
        assert kwargs["idempotency_key"] == str(_IDEMPOTENCY_KEY)

    @pytest.mark.asyncio
    async def test_uses_calendar_id_from_credentials(self) -> None:
        svc, event_repo, oauth_repo, auth, _ = _make_service()
        event_repo.get_by_id.return_value = _make_event(status="confirmed")
        event_repo.update_status.return_value = _make_event(status="synced")
        auth.get_valid_token.return_value = _ACCESS_TOKEN
        oauth_repo.get_by_user_id.return_value = _make_cred(calendar_id="work@group.calendar")

        mock_create = AsyncMock(return_value=_GOOGLE_EVENT_ID)
        with patch(
            "src.services.event_service.calendar_service.create_event", new=mock_create
        ):
            await svc.sync_event(_EVENT_ID)

        _, kwargs = mock_create.call_args
        assert kwargs["calendar_id"] == "work@group.calendar"

    @pytest.mark.asyncio
    async def test_falls_back_to_primary_when_no_calendar_id(self) -> None:
        svc, event_repo, oauth_repo, auth, _ = _make_service()
        event_repo.get_by_id.return_value = _make_event(status="confirmed")
        event_repo.update_status.return_value = _make_event(status="synced")
        auth.get_valid_token.return_value = _ACCESS_TOKEN
        cred = _make_cred()
        cred.calendar_id = None  # type: ignore[assignment]
        oauth_repo.get_by_user_id.return_value = cred

        mock_create = AsyncMock(return_value=_GOOGLE_EVENT_ID)
        with patch(
            "src.services.event_service.calendar_service.create_event", new=mock_create
        ):
            await svc.sync_event(_EVENT_ID)

        _, kwargs = mock_create.call_args
        assert kwargs["calendar_id"] == "primary"


# ---------------------------------------------------------------------------
# sync_event — wrong status / not found guards
# ---------------------------------------------------------------------------


class TestSyncEventGuards:
    @pytest.mark.asyncio
    async def test_raises_event_not_found_when_missing(self) -> None:
        svc, event_repo, *_ = _make_service()
        event_repo.get_by_id.return_value = None

        with pytest.raises(EventNotFoundError):
            await svc.sync_event(_EVENT_ID)

    @pytest.mark.asyncio
    async def test_returns_unchanged_when_status_is_pending(self) -> None:
        svc, event_repo, *_ = _make_service()
        event = _make_event(status="pending")
        event_repo.get_by_id.return_value = event

        result = await svc.sync_event(_EVENT_ID)

        assert result is event
        event_repo.update_status.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_unchanged_when_already_synced(self) -> None:
        svc, event_repo, *_ = _make_service()
        event = _make_event(status="synced")
        event_repo.get_by_id.return_value = event

        result = await svc.sync_event(_EVENT_ID)

        assert result is event
        event_repo.update_status.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_unchanged_when_already_failed(self) -> None:
        svc, event_repo, *_ = _make_service()
        event = _make_event(status="failed")
        event_repo.get_by_id.return_value = event

        result = await svc.sync_event(_EVENT_ID)

        assert result is event
        event_repo.update_status.assert_not_awaited()


# ---------------------------------------------------------------------------
# sync_event — failure paths: status MUST become 'failed' before exception
# ---------------------------------------------------------------------------


class TestSyncEventFailureTransitions:
    """Core guarantee: confirmed → failed is flushed before any exception."""

    @pytest.mark.asyncio
    async def test_no_credentials_marks_failed_then_raises_token_error(self) -> None:
        svc, event_repo, oauth_repo, auth, _ = _make_service()
        event_repo.get_by_id.return_value = _make_event(status="confirmed")
        auth.get_valid_token.return_value = None  # no credentials

        with pytest.raises(TokenExpiredError):
            await svc.sync_event(_EVENT_ID)

        # 'failed' status must have been written before the exception
        args, _ = event_repo.update_status.call_args
        assert args == (_EVENT_ID, "failed")
        # retry_count must be incremented
        event_repo.increment_retry.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_credentials_update_status_call_contains_failed(self) -> None:
        """Verify the exact first positional arg is 'failed'."""
        svc, event_repo, oauth_repo, auth, _ = _make_service()
        event_repo.get_by_id.return_value = _make_event(status="confirmed")
        auth.get_valid_token.return_value = None

        with pytest.raises(TokenExpiredError):
            await svc.sync_event(_EVENT_ID)

        args, _ = event_repo.update_status.call_args
        assert args[1] == "failed"

    @pytest.mark.asyncio
    async def test_google_api_error_marks_failed_then_reraises(self) -> None:
        svc, event_repo, oauth_repo, auth, _ = _make_service()
        event_repo.get_by_id.return_value = _make_event(status="confirmed")
        auth.get_valid_token.return_value = _ACCESS_TOKEN
        oauth_repo.get_by_user_id.return_value = _make_cred()

        api_error = GoogleApiError("quota exceeded")
        with (
            patch(
                "src.services.event_service.calendar_service.create_event",
                new=AsyncMock(side_effect=api_error),
            ),
            pytest.raises(GoogleApiError, match="quota exceeded"),
        ):
            await svc.sync_event(_EVENT_ID)

        # Status must be 'failed' and retry incremented BEFORE exception exits
        args, _ = event_repo.update_status.call_args
        assert args[1] == "failed"
        event_repo.increment_retry.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_google_api_error_stores_error_message(self) -> None:
        svc, event_repo, oauth_repo, auth, _ = _make_service()
        event_repo.get_by_id.return_value = _make_event(status="confirmed")
        auth.get_valid_token.return_value = _ACCESS_TOKEN
        oauth_repo.get_by_user_id.return_value = _make_cred()
        error_msg = "Google API error 503 on create_event"

        with (
            patch(
                "src.services.event_service.calendar_service.create_event",
                new=AsyncMock(side_effect=GoogleApiError(error_msg)),
            ),
            pytest.raises(GoogleApiError),
        ):
            await svc.sync_event(_EVENT_ID)

        _, kwargs = event_repo.update_status.call_args
        assert kwargs["last_error"] == error_msg

    @pytest.mark.asyncio
    async def test_mark_failed_called_before_exception_propagates(self) -> None:
        """Verify ordering: update_status('failed') happens before raise."""
        call_order: list[str] = []

        svc, event_repo, oauth_repo, auth, _ = _make_service()
        event_repo.get_by_id.return_value = _make_event(status="confirmed")
        auth.get_valid_token.return_value = None

        async def track_update_status(event_id: int, status: str, **_kw: object) -> None:
            call_order.append(f"update_status:{status}")
            return None

        async def track_increment_retry(event_id: int, error: str) -> None:
            call_order.append("increment_retry")
            return None

        event_repo.update_status.side_effect = track_update_status
        event_repo.increment_retry.side_effect = track_increment_retry

        try:
            await svc.sync_event(_EVENT_ID)
        except TokenExpiredError:
            call_order.append("exception_raised")

        assert call_order == ["update_status:failed", "increment_retry", "exception_raised"]


# ---------------------------------------------------------------------------
# get_pending_events_for_retry
# ---------------------------------------------------------------------------


class TestGetPendingEventsForRetry:
    @pytest.mark.asyncio
    async def test_delegates_to_repo_with_60s_threshold(self) -> None:
        svc, event_repo, *_ = _make_service()
        expected = [_make_event(status="confirmed")]
        event_repo.get_pending_for_retry.return_value = expected

        result = await svc.get_pending_events_for_retry()

        event_repo.get_pending_for_retry.assert_awaited_once_with(older_than_seconds=60)
        assert result is expected

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_none_pending(self) -> None:
        svc, event_repo, *_ = _make_service()
        event_repo.get_pending_for_retry.return_value = []

        result = await svc.get_pending_events_for_retry()

        assert result == []
