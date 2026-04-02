"""Unit tests for calendar_service — Stage 6.

Strategy
--------
All tests mock ``src.services.calendar_service._build_service`` so no real
HTTP calls are made.  The public async functions are exercised end-to-end,
including the tenacity retry layer inside the private sync helpers.

Idempotency tests confirm that the normalised ``idempotency_key`` is always
forwarded as the event ``id`` field, making retries safe against duplicates.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError

from src.exceptions import GoogleApiError
from src.schemas.parsed_message import ParsedEvent
from src.services.calendar_service import (
    _normalize_idempotency_key,
    check_conflicts,
    create_event,
    delete_event,
    list_upcoming,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TOKEN = "fake-access-token"
_CAL_ID = "primary"
_UUID_KEY = "123e4567-e89b-12d3-a456-426614174000"
_NORMALIZED_KEY = "123e4567e89b12d3a456426614174000"  # hyphens removed, 32 chars


def _make_http_error(status: int) -> HttpError:
    resp = MagicMock()
    resp.status = status
    resp.reason = "error"
    return HttpError(resp=resp, content=b"error")


def _make_service_mock(insert_return: dict[str, Any] | None = None) -> MagicMock:
    """Return a mock ``googleapiclient`` service object."""
    service = MagicMock()
    events = service.events.return_value

    if insert_return is not None:
        events.insert.return_value.execute.return_value = insert_return

    return service


def _parsed_event(
    title: str = "Test event",
    start: datetime | None = None,
    end: datetime | None = None,
) -> ParsedEvent:
    if start is None:
        start = datetime(2026, 6, 1, 18, 0, tzinfo=UTC)
    return ParsedEvent(title=title, start_at=start, end_at=end)


# ---------------------------------------------------------------------------
# _normalize_idempotency_key
# ---------------------------------------------------------------------------


class TestNormalizeIdempotencyKey:
    def test_uuid_strips_hyphens(self) -> None:
        result = _normalize_idempotency_key(_UUID_KEY)
        assert result == _NORMALIZED_KEY

    def test_result_is_lowercase(self) -> None:
        result = _normalize_idempotency_key("ABCDEF1234")
        assert result == result.lower()

    def test_result_is_alphanumeric_only(self) -> None:
        result = _normalize_idempotency_key("hello-world_test 123")
        assert result.isalnum()

    def test_minimum_length_padded(self) -> None:
        result = _normalize_idempotency_key("ab")
        assert len(result) >= 5

    def test_truncated_to_1024(self) -> None:
        result = _normalize_idempotency_key("a" * 2000)
        assert len(result) == 1024


# ---------------------------------------------------------------------------
# create_event
# ---------------------------------------------------------------------------


class TestCreateEvent:
    @pytest.mark.asyncio
    async def test_happy_path_returns_google_event_id(self) -> None:
        service = _make_service_mock(
            insert_return={"id": _NORMALIZED_KEY, "summary": "Test event"}
        )
        with patch("src.services.calendar_service._build_service", return_value=service):
            result = await create_event(_TOKEN, _CAL_ID, _parsed_event(), _UUID_KEY)

        assert result == _NORMALIZED_KEY

    @pytest.mark.asyncio
    async def test_idempotency_key_sent_as_event_id(self) -> None:
        """The normalised key must be forwarded as the Google event ``id`` field."""
        service = _make_service_mock(insert_return={"id": _NORMALIZED_KEY})
        with patch("src.services.calendar_service._build_service", return_value=service):
            await create_event(_TOKEN, _CAL_ID, _parsed_event(), _UUID_KEY)

        inserted_body: dict[str, Any] = (
            service.events.return_value.insert.call_args.kwargs["body"]
        )
        assert inserted_body["id"] == _NORMALIZED_KEY

    @pytest.mark.asyncio
    async def test_end_at_defaults_to_one_hour_after_start(self) -> None:
        start = datetime(2026, 6, 1, 18, 0, tzinfo=UTC)
        service = _make_service_mock(insert_return={"id": _NORMALIZED_KEY})
        with patch("src.services.calendar_service._build_service", return_value=service):
            await create_event(_TOKEN, _CAL_ID, _parsed_event(start=start), _UUID_KEY)

        body: dict[str, Any] = (
            service.events.return_value.insert.call_args.kwargs["body"]
        )
        assert "19:00:00" in body["end"]["dateTime"]

    @pytest.mark.asyncio
    async def test_explicit_end_at_is_used(self) -> None:
        start = datetime(2026, 6, 1, 18, 0, tzinfo=UTC)
        end = datetime(2026, 6, 1, 20, 0, tzinfo=UTC)
        service = _make_service_mock(insert_return={"id": _NORMALIZED_KEY})
        with patch("src.services.calendar_service._build_service", return_value=service):
            await create_event(
                _TOKEN, _CAL_ID, _parsed_event(start=start, end=end), _UUID_KEY
            )

        body: dict[str, Any] = (
            service.events.return_value.insert.call_args.kwargs["body"]
        )
        assert "20:00:00" in body["end"]["dateTime"]

    @pytest.mark.asyncio
    async def test_retries_on_429_then_succeeds(self) -> None:
        """First call raises 429; second succeeds — one retry, no duplicate."""
        service_fail = MagicMock()
        service_ok = _make_service_mock(insert_return={"id": _NORMALIZED_KEY})

        call_count = 0

        def build_side_effect(*_args: Any, **_kwargs: Any) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                service_fail.events.return_value.insert.return_value.execute.side_effect = (
                    _make_http_error(429)
                )
                return service_fail
            return service_ok

        with patch("src.services.calendar_service._build_service", side_effect=build_side_effect):
            result = await create_event(_TOKEN, _CAL_ID, _parsed_event(), _UUID_KEY)

        assert result == _NORMALIZED_KEY
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_503_then_succeeds(self) -> None:
        call_count = 0

        def build_side_effect(*_args: Any, **_kwargs: Any) -> MagicMock:
            nonlocal call_count
            call_count += 1
            svc = MagicMock()
            if call_count < 3:
                svc.events.return_value.insert.return_value.execute.side_effect = (
                    _make_http_error(503)
                )
            else:
                svc.events.return_value.insert.return_value.execute.return_value = {
                    "id": _NORMALIZED_KEY
                }
            return svc

        with patch("src.services.calendar_service._build_service", side_effect=build_side_effect):
            result = await create_event(_TOKEN, _CAL_ID, _parsed_event(), _UUID_KEY)

        assert result == _NORMALIZED_KEY
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_google_api_error_after_all_retries_exhausted(self) -> None:
        service = MagicMock()
        service.events.return_value.insert.return_value.execute.side_effect = (
            _make_http_error(503)
        )
        with (
            patch("src.services.calendar_service._build_service", return_value=service),
            pytest.raises(GoogleApiError),
        ):
            await create_event(_TOKEN, _CAL_ID, _parsed_event(), _UUID_KEY)

    @pytest.mark.asyncio
    async def test_non_retryable_400_raises_immediately(self) -> None:
        """400 errors must NOT be retried — they indicate a bad request."""
        service = MagicMock()
        service.events.return_value.insert.return_value.execute.side_effect = (
            _make_http_error(400)
        )
        with (
            patch("src.services.calendar_service._build_service", return_value=service),
            pytest.raises(GoogleApiError),
        ):
            await create_event(_TOKEN, _CAL_ID, _parsed_event(), _UUID_KEY)

        # Only 1 call — no retries for 400
        assert service.events.return_value.insert.return_value.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_idempotency_key_is_same_on_every_retry(self) -> None:
        """Every retry must send the same event id — this is the core guarantee."""
        inserted_bodies: list[dict[str, Any]] = []
        call_count = 0

        def build_side_effect(*_args: Any, **_kwargs: Any) -> MagicMock:
            nonlocal call_count
            call_count += 1
            svc = MagicMock()
            if call_count < 3:
                svc.events.return_value.insert.return_value.execute.side_effect = (
                    _make_http_error(503)
                )
            else:
                svc.events.return_value.insert.return_value.execute.return_value = {
                    "id": _NORMALIZED_KEY
                }
            # Capture the body on insert()
            original_insert = svc.events.return_value.insert

            def capturing_insert(**kwargs: Any) -> MagicMock:
                inserted_bodies.append(kwargs.get("body", {}))
                return original_insert(**kwargs)

            svc.events.return_value.insert = capturing_insert
            return svc

        with patch("src.services.calendar_service._build_service", side_effect=build_side_effect):
            await create_event(_TOKEN, _CAL_ID, _parsed_event(), _UUID_KEY)

        ids = [b.get("id") for b in inserted_bodies]
        assert all(i == _NORMALIZED_KEY for i in ids), f"Inconsistent ids across retries: {ids}"


# ---------------------------------------------------------------------------
# list_upcoming
# ---------------------------------------------------------------------------


class TestListUpcoming:
    @pytest.mark.asyncio
    async def test_returns_items_list(self) -> None:
        events = [{"id": "ev1", "summary": "A"}, {"id": "ev2", "summary": "B"}]
        service = MagicMock()
        service.events.return_value.list.return_value.execute.return_value = {
            "items": events
        }
        with patch("src.services.calendar_service._build_service", return_value=service):
            result = await list_upcoming(_TOKEN, _CAL_ID, count=2)

        assert result == events

    @pytest.mark.asyncio
    async def test_empty_calendar_returns_empty_list(self) -> None:
        service = MagicMock()
        service.events.return_value.list.return_value.execute.return_value = {}
        with patch("src.services.calendar_service._build_service", return_value=service):
            result = await list_upcoming(_TOKEN, _CAL_ID)

        assert result == []

    @pytest.mark.asyncio
    async def test_raises_google_api_error_on_http_error(self) -> None:
        service = MagicMock()
        service.events.return_value.list.return_value.execute.side_effect = (
            _make_http_error(403)
        )
        with (
            patch("src.services.calendar_service._build_service", return_value=service),
            pytest.raises(GoogleApiError),
        ):
            await list_upcoming(_TOKEN, _CAL_ID)


# ---------------------------------------------------------------------------
# delete_event
# ---------------------------------------------------------------------------


class TestDeleteEvent:
    @pytest.mark.asyncio
    async def test_returns_true_on_success(self) -> None:
        service = MagicMock()
        service.events.return_value.delete.return_value.execute.return_value = None
        with patch("src.services.calendar_service._build_service", return_value=service):
            result = await delete_event(_TOKEN, _CAL_ID, "ev123")

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_on_404(self) -> None:
        service = MagicMock()
        service.events.return_value.delete.return_value.execute.side_effect = (
            _make_http_error(404)
        )
        with patch("src.services.calendar_service._build_service", return_value=service):
            result = await delete_event(_TOKEN, _CAL_ID, "missing-event")

        assert result is False

    @pytest.mark.asyncio
    async def test_raises_google_api_error_on_500(self) -> None:
        service = MagicMock()
        service.events.return_value.delete.return_value.execute.side_effect = (
            _make_http_error(500)
        )
        with (
            patch("src.services.calendar_service._build_service", return_value=service),
            pytest.raises(GoogleApiError),
        ):
            await delete_event(_TOKEN, _CAL_ID, "ev123")


# ---------------------------------------------------------------------------
# check_conflicts
# ---------------------------------------------------------------------------


class TestCheckConflicts:
    @pytest.mark.asyncio
    async def test_returns_overlapping_events(self) -> None:
        start = datetime(2026, 6, 1, 18, 0, tzinfo=UTC)
        end = datetime(2026, 6, 1, 20, 0, tzinfo=UTC)
        overlap = [{"id": "conf1", "summary": "Conflict"}]
        service = MagicMock()
        service.events.return_value.list.return_value.execute.return_value = {
            "items": overlap
        }
        with patch("src.services.calendar_service._build_service", return_value=service):
            result = await check_conflicts(_TOKEN, _CAL_ID, start, end)

        assert result == overlap

    @pytest.mark.asyncio
    async def test_no_conflicts_returns_empty_list(self) -> None:
        start = datetime(2026, 6, 1, 18, 0, tzinfo=UTC)
        end = datetime(2026, 6, 1, 20, 0, tzinfo=UTC)
        service = MagicMock()
        service.events.return_value.list.return_value.execute.return_value = {}
        with patch("src.services.calendar_service._build_service", return_value=service):
            result = await check_conflicts(_TOKEN, _CAL_ID, start, end)

        assert result == []

    @pytest.mark.asyncio
    async def test_raises_google_api_error_on_http_error(self) -> None:
        start = datetime(2026, 6, 1, 18, 0, tzinfo=UTC)
        end = datetime(2026, 6, 1, 20, 0, tzinfo=UTC)
        service = MagicMock()
        service.events.return_value.list.return_value.execute.side_effect = (
            _make_http_error(503)
        )
        with (
            patch("src.services.calendar_service._build_service", return_value=service),
            pytest.raises(GoogleApiError),
        ):
            await check_conflicts(_TOKEN, _CAL_ID, start, end)
