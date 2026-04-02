"""User Service — Stage 7: CRUD for bot users."""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repositories.user_repo import UserRepository
from src.models.user import User

logger = structlog.get_logger(__name__)


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = UserRepository(session)

    async def get_or_create(self, telegram_id: int) -> tuple[User, bool]:
        """Return (user, created). created=True when a new user was inserted."""
        user = await self._repo.get_by_telegram_id(telegram_id)
        if user is not None:
            return user, False
        user = await self._repo.create(telegram_id=telegram_id)
        logger.info("user_created", telegram_id=telegram_id, user_id=user.id)
        return user, True

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        return await self._repo.get_by_telegram_id(telegram_id)

    async def get_by_id(self, user_id: int) -> User | None:
        return await self._repo.get_by_id(user_id)

    async def update_timezone(self, user_id: int, timezone: str) -> User | None:
        user = await self._repo.update_timezone(user_id, timezone)
        if user is not None:
            logger.info("user_timezone_updated", user_id=user_id, timezone=timezone)
        return user

    async def delete(self, user_id: int) -> bool:
        deleted = await self._repo.delete(user_id)
        if deleted:
            logger.info("user_deleted", user_id=user_id)
        return deleted
