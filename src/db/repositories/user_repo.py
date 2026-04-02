from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: int) -> User | None:
        result = await self._session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self._session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def create(self, telegram_id: int, timezone: str = "UTC") -> User:
        user = User(telegram_id=telegram_id, timezone=timezone)
        self._session.add(user)
        await self._session.flush()
        await self._session.refresh(user)
        return user

    async def update_timezone(self, user_id: int, timezone: str) -> User | None:
        user = await self.get_by_id(user_id)
        if user is None:
            return None
        user.timezone = timezone
        await self._session.flush()
        return user

    async def delete(self, user_id: int) -> bool:
        user = await self.get_by_id(user_id)
        if user is None:
            return False
        await self._session.delete(user)
        await self._session.flush()
        return True
