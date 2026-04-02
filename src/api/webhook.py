"""POST /webhook/telegram — receives Telegram updates and feeds them to aiogram."""

from aiogram.types import Update
from fastapi import APIRouter, Depends, Request

from src.bot.setup import bot, dp
from src.security.webhook_verify import verify_telegram_secret

router = APIRouter()


@router.post(
    "/webhook/telegram",
    dependencies=[Depends(verify_telegram_secret)],
)
async def telegram_webhook(request: Request) -> dict[str, bool]:
    """Deserialise the incoming Telegram update and dispatch it."""
    payload = await request.json()
    update = Update.model_validate(payload)
    await dp.feed_update(bot, update)
    return {"ok": True}
