import hmac

from fastapi import Header, HTTPException, status

from src.config import settings


async def verify_telegram_secret(
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> None:
    """FastAPI dependency that verifies Telegram webhook secret token."""
    if x_telegram_bot_api_secret_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Telegram-Bot-Api-Secret-Token header",
        )
    if not hmac.compare_digest(
        x_telegram_bot_api_secret_token,
        settings.telegram_webhook_secret,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook secret token",
        )
