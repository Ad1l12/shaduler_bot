"""Handlers for /connect and /disconnect commands."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.auth_service import AuthService
from src.services.user_service import UserService

router = Router()


@router.message(Command("connect"))
async def cmd_connect(message: Message, session: AsyncSession) -> None:
    """Send the Google OAuth URL so the user can authorise the bot."""
    if message.from_user is None:
        return

    user_service = UserService(session)
    user, _ = await user_service.get_or_create(message.from_user.id)

    auth_service = AuthService(session)
    url = auth_service.generate_auth_url(user.id)

    await message.answer(
        f'<a href="{url}">Подключить Google Calendar</a>\n\n'
        "Нажмите ссылку, пройдите авторизацию и вернитесь в бот.",
        disable_web_page_preview=True,
    )


@router.message(Command("disconnect"))
async def cmd_disconnect(message: Message, session: AsyncSession) -> None:
    """Revoke stored Google credentials and inform the user."""
    if message.from_user is None:
        return

    user_service = UserService(session)
    user = await user_service.get_by_telegram_id(message.from_user.id)

    if user is None:
        await message.answer("У вас нет подключённого Google аккаунта.")
        return

    auth_service = AuthService(session)
    await auth_service.revoke_access(user.id)
    await message.answer(
        "✅ Google Calendar отключён. "
        "Используйте /connect для повторного подключения."
    )
