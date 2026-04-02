"""Integration tests: webhook → parse → pending → confirm → sync.

Full flow through the real FastAPI app and real SQLAlchemy sessions on an
in-memory SQLite DB.  Google Calendar API is mocked at the function level —
no HTTP calls to Google are made.

Flow under test
---------------
1. POST /webhook/telegram  with a text message
   → aiogram dispatches to events.handle_text
   → parser_service.parse_message
   → EventService.create_pending_event  (status = 'pending')
   → bot replies with preview + keyboard

2. POST /webhook/telegram  with a callback_query (ConfirmEventCallback)
   → aiogram dispatches to callbacks.on_confirm_event
   → EventService.confirm_event  (pending → confirmed)
   → EventService.sync_event     (confirmed → synced)
   → calendar_service.create_event called with idempotency_key
   → bot edits the preview message
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards import ConfirmEventCallback
from src.db.repositories.event_repo import EventRepository
from src.db.repositories.user_repo import UserRepository

_SECRET = "test-webhook-secret"
_HEADERS = {
    "X-Telegram-Bot-Api-Secret-Token": _SECRET,
    "Content-Type": "application/json",
}
_TG_USER_ID = 111222333
_FUTURE_DATE = (datetime.now(UTC) + timedelta(days=1)).strftime("%d.%m")


def _text_update(text: str, update_id: int = 1) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": int(datetime.now(UTC).timestamp()),
            "chat": {"id": _TG_USER_ID, "type": "private"},
            "from": {
                "id": _TG_USER_ID,
                "is_bot": False,
                "first_name": "Test",
                "language_code": "ru",
            },
            "text": text,
        },
    }


def _callback_update(callback_data: str, update_id: int = 2) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": "cq123",
            "chat_instance": "-1234567890",
            "from": {
                "id": _TG_USER_ID,
                "is_bot": False,
                "first_name": "Test",
                "language_code": "ru",
            },
            "message": {
                "message_id": 1,
                "date": int(datetime.now(UTC).timestamp()),
                "chat": {"id": _TG_USER_ID, "type": "private"},
                "from": {
                    "id": 12345,
                    "is_bot": True,
                    "first_name": "Bot",
                },
                "text": "preview text",
            },
            "data": callback_data,
        },
    }


# ── Helper: silence aiogram Telegram API calls ────────────────────────────────

def _mock_bot_calls() -> Any:
    """Context manager that stubs outgoing Telegram Bot API calls."""
    return patch(
        "aiogram.client.bot.Bot.session",
        new_callable=lambda: property(lambda self: AsyncMock()),  # type: ignore[arg-type]
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_text_message_creates_pending_event(
    http_client: AsyncClient,
    db_session: AsyncSession,
    mock_calendar_service: dict[str, AsyncMock],
) -> None:
    """Text → parse → pending event saved in DB."""
    send_mock = AsyncMock()
    with patch("aiogram.client.session.aiohttp.AiohttpSession.make_request", send_mock):
        resp = await http_client.post(
            "/webhook/telegram",
            headers=_HEADERS,
            content=json.dumps(_text_update("завтра в 18 тренировка")),
        )

    assert resp.status_code == 200

    user_repo = UserRepository(db_session)
    user = await user_repo.get_by_telegram_id(_TG_USER_ID)
    assert user is not None

    # Event is pending, not confirmed — use direct query
    from sqlalchemy import select

    from src.models.event import Event
    result = await db_session.execute(
        select(Event).where(Event.user_id == user.id, Event.status == "pending")
    )
    pending = result.scalars().all()
    assert len(pending) == 1
    assert pending[0].title == "тренировка"


@pytest.mark.asyncio
async def test_unparseable_message_creates_no_event(
    http_client: AsyncClient,
    db_session: AsyncSession,
    mock_calendar_service: dict[str, AsyncMock],
) -> None:
    """Text with no date/time → no event created."""
    send_mock = AsyncMock()
    with patch("aiogram.client.session.aiohttp.AiohttpSession.make_request", send_mock):
        resp = await http_client.post(
            "/webhook/telegram",
            headers=_HEADERS,
            content=json.dumps(_text_update("привет как дела")),
        )

    assert resp.status_code == 200

    from sqlalchemy import func, select

    from src.models.event import Event
    count = (await db_session.execute(select(func.count()).select_from(Event))).scalar()
    assert count == 0


@pytest.mark.asyncio
async def test_confirm_callback_syncs_event(
    http_client: AsyncClient,
    db_session: AsyncSession,
    mock_calendar_service: dict[str, AsyncMock],
) -> None:
    """Confirm callback → event transitions pending→confirmed→synced.

    We manually create a pending event and user to avoid depending on the
    text-message parse step.
    """
    from src.db.repositories.user_repo import UserRepository

    # Set up: user with valid (mocked) Google credentials
    user_repo = UserRepository(db_session)
    user = await user_repo.create(telegram_id=_TG_USER_ID)

    event_repo = EventRepository(db_session)
    event = await event_repo.create(
        user_id=user.id,
        title="Дедлайн проекта",
        start_at=datetime.now(UTC) + timedelta(days=2),
    )
    await db_session.commit()

    # Mock AuthService.get_valid_token so sync doesn't need real credentials
    with patch(
        "src.services.event_service.AuthService.get_valid_token",
        new=AsyncMock(return_value="ya29.mock-token"),
    ):
        # First: move to confirmed (simulating the /confirm callback)
        await event_repo.update_status(event.id, "confirmed")
        await db_session.commit()

        callback_data = ConfirmEventCallback(event_id=event.id).pack()
        send_mock = AsyncMock()
        with patch("aiogram.client.session.aiohttp.AiohttpSession.make_request", send_mock):
            resp = await http_client.post(
                "/webhook/telegram",
                headers=_HEADERS,
                content=json.dumps(_callback_update(callback_data)),
            )

    assert resp.status_code == 200

    await db_session.refresh(event)
    assert event.status == "synced"
    assert event.external_id == "googleeventid123"
    mock_calendar_service["create_event"].assert_awaited_once()


@pytest.mark.asyncio
async def test_confirm_callback_with_no_credentials_marks_failed(
    http_client: AsyncClient,
    db_session: AsyncSession,
    mock_calendar_service: dict[str, AsyncMock],
) -> None:
    """Confirm with no Google credentials → event marked failed, not stuck confirmed."""
    from src.db.repositories.user_repo import UserRepository

    user_repo = UserRepository(db_session)
    user = await user_repo.create(telegram_id=_TG_USER_ID)

    event_repo = EventRepository(db_session)
    event = await event_repo.create(
        user_id=user.id,
        title="Встреча",
        start_at=datetime.now(UTC) + timedelta(days=1),
    )
    await event_repo.update_status(event.id, "confirmed")
    await db_session.commit()

    # No credentials row in DB — get_valid_token returns None
    callback_data = ConfirmEventCallback(event_id=event.id).pack()
    send_mock = AsyncMock()
    with patch("aiogram.client.session.aiohttp.AiohttpSession.make_request", send_mock):
        resp = await http_client.post(
            "/webhook/telegram",
            headers=_HEADERS,
            content=json.dumps(_callback_update(callback_data)),
        )

    assert resp.status_code == 200

    await db_session.refresh(event)
    assert event.status == "failed"
    assert event.retry_count == 1
    mock_calendar_service["create_event"].assert_not_awaited()


@pytest.mark.asyncio
async def test_webhook_rejects_invalid_secret(
    http_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Requests with wrong secret must be rejected with 401."""
    resp = await http_client.post(
        "/webhook/telegram",
        headers={
            "X-Telegram-Bot-Api-Secret-Token": "wrong-secret",
            "Content-Type": "application/json",
        },
        content=json.dumps(_text_update("завтра в 18 тренировка")),
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_webhook_rejects_missing_secret(
    http_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Requests without the secret header must be rejected with 401."""
    resp = await http_client.post(
        "/webhook/telegram",
        headers={"Content-Type": "application/json"},
        content=json.dumps(_text_update("завтра в 18 тренировка")),
    )
    assert resp.status_code == 401
