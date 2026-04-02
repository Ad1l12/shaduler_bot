"""Handlers for /list, /timezone and free-text event creation."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards import confirm_keyboard
from src.db.repositories.event_repo import EventRepository
from src.services.event_service import EventService
from src.services.parser_service import parse_message
from src.services.user_service import UserService

router = Router()


@router.message(Command("list"))
async def cmd_list(message: Message, session: AsyncSession) -> None:
    """Show the 5 nearest synced events for the current user."""
    if message.from_user is None:
        return

    user_service = UserService(session)
    user = await user_service.get_by_telegram_id(message.from_user.id)

    if user is None:
        await message.answer("Сначала подключите Google Calendar: /connect")
        return

    event_repo = EventRepository(session)
    events = await event_repo.list_upcoming(user.id, count=5)

    if not events:
        await message.answer("Нет предстоящих событий.")
        return

    lines = [f"• {e.start_at.strftime('%d.%m %H:%M')} — {e.title}" for e in events]
    await message.answer("📅 Предстоящие события:\n" + "\n".join(lines))


@router.message(Command("timezone"))
async def cmd_timezone(message: Message, session: AsyncSession) -> None:
    """Set the user's timezone. Usage: /timezone Europe/Moscow"""
    if message.from_user is None:
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Укажите часовой пояс. Пример:\n"
            "<code>/timezone Europe/Moscow</code>"
        )
        return

    tz_name = parts[1].strip()
    try:
        ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, KeyError):
        await message.answer(f"Неизвестный часовой пояс: <code>{tz_name}</code>")
        return

    user_service = UserService(session)
    user, _ = await user_service.get_or_create(message.from_user.id)
    await user_service.update_timezone(user.id, tz_name)
    await message.answer(f"✅ Часовой пояс установлен: <code>{tz_name}</code>")


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: Message, session: AsyncSession) -> None:
    """Parse a natural-language message and offer to create a calendar event."""
    if message.from_user is None or message.text is None:
        return

    user_service = UserService(session)
    user, _ = await user_service.get_or_create(message.from_user.id)

    now = datetime.now(UTC)
    parsed = parse_message(message.text, user.timezone, now)

    if parsed is None:
        await message.answer(
            "Не удалось распознать событие 🤔\n"
            "Попробуйте, например: <i>завтра в 18 тренировка</i>"
        )
        return

    event_service = EventService(session)
    event = await event_service.create_pending_event(user.id, parsed)

    start_str = parsed.start_at.strftime("%d.%m.%Y в %H:%M")
    await message.answer(
        f"📅 <b>{parsed.title}</b>\n"
        f"🕐 {start_str}\n\n"
        "Создать событие в Google Calendar?",
        reply_markup=confirm_keyboard(event.id),
    )
