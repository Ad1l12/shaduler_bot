"""Handlers for inline-button callback queries (confirm / cancel event creation)."""

import structlog
from aiogram import Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards import CancelEventCallback, ConfirmEventCallback
from src.exceptions import EventNotFoundError, GoogleApiError, TokenExpiredError
from src.services.event_service import EventService

logger = structlog.get_logger(__name__)

router = Router()


@router.callback_query(ConfirmEventCallback.filter())
async def on_confirm_event(
    query: CallbackQuery,
    callback_data: ConfirmEventCallback,
    session: AsyncSession,
) -> None:
    """Confirm → sync the pending event to Google Calendar."""
    await query.answer()

    # Guard: message must be an accessible Message (not deleted/inaccessible)
    if not isinstance(query.message, Message):
        return

    event_service = EventService(session)

    # Step 1: move pending → confirmed
    try:
        await event_service.confirm_event(callback_data.event_id)
    except EventNotFoundError:
        await query.message.edit_text("❌ Событие не найдено.")
        return

    # Step 2: sync confirmed → Google Calendar (synced or failed)
    # On failure, EventService flushes status='failed' before raising,
    # so the middleware's session.commit() will persist the failed state.
    try:
        event = await event_service.sync_event(callback_data.event_id)
    except TokenExpiredError:
        await query.message.edit_text(
            "❌ Google Calendar не подключён.\n"
            "Используйте /connect для авторизации."
        )
        return
    except GoogleApiError:
        logger.error("sync_failed_in_callback", event_id=callback_data.event_id)
        await query.message.edit_text(
            "❌ Не удалось создать событие в Google Calendar.\n"
            "Попробуйте ещё раз позже."
        )
        return

    start_str = event.start_at.strftime("%d.%m.%Y в %H:%M")
    await query.message.edit_text(
        f"✅ Создано: <b>{event.title}</b>\n"
        f"📅 {start_str}"
    )


@router.callback_query(CancelEventCallback.filter())
async def on_cancel_event(
    query: CallbackQuery,
    callback_data: CancelEventCallback,  # noqa: ARG001
) -> None:
    """User declined — dismiss the preview message."""
    await query.answer("Отменено")
    if not isinstance(query.message, Message):
        return
    await query.message.edit_text("❌ Создание отменено.")
