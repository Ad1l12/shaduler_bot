"""Handlers for /start and /help commands."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()

_HELP_TEXT = (
    "📅 <b>Telegram → Google Calendar Bot</b>\n\n"
    "Напишите о событии свободным текстом — бот добавит его в ваш календарь:\n"
    "  <i>завтра в 18 тренировка</i>\n"
    "  <i>в пятницу в 20 ужин с друзьями</i>\n"
    "  <i>15 мая в 10:30 собеседование</i>\n\n"
    "<b>Команды:</b>\n"
    "/connect — подключить Google Calendar\n"
    "/disconnect — отключить Google Calendar\n"
    "/list — ближайшие 5 событий\n"
    "/timezone — установить часовой пояс (пример: /timezone Europe/Moscow)\n"
    "/help — эта справка"
)


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    if message.from_user is None:
        return
    name = message.from_user.first_name or "друг"
    await message.answer(f"Привет, {name}!\n\n{_HELP_TEXT}")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(_HELP_TEXT)
