"""aiogram middlewares: DB session injection and rate limiting."""

from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from src.db.session import AsyncSessionFactory

logger = structlog.get_logger(__name__)


class DbSessionMiddleware(BaseMiddleware):
    """Open an AsyncSession, inject it as ``data["session"]``, commit on success.

    If the handler raises an unhandled exception the session's context manager
    rolls back.  Bot handlers are expected to catch all business-logic
    exceptions (GoogleApiError, TokenExpiredError, …) and reply to the user,
    so a successful handler return always means a safe commit.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with AsyncSessionFactory() as session:
            data["session"] = session
            result = await handler(event, data)
            await session.commit()
            return result


class RateLimitMiddleware(BaseMiddleware):
    """Allow at most *limit* messages per *window* seconds per user.

    Non-Message updates (callback queries, etc.) are passed through unchanged.
    Uses an in-memory window — no Redis required for MVP.
    """

    def __init__(self, limit: int = 10, window: int = 60) -> None:
        self._limit = limit
        self._window = window
        self._history: dict[int, list[datetime]] = defaultdict(list)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message) or event.from_user is None:
            return await handler(event, data)

        user_id = event.from_user.id
        now = datetime.now(UTC)
        cutoff = now - timedelta(seconds=self._window)

        # Evict timestamps outside the sliding window
        self._history[user_id] = [t for t in self._history[user_id] if t > cutoff]

        if len(self._history[user_id]) >= self._limit:
            logger.warning("rate_limit_hit", user_id=user_id)
            await event.answer("⏳ Слишком много сообщений. Подождите немного.")
            return None

        self._history[user_id].append(now)
        return await handler(event, data)
