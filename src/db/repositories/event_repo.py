import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.event import Event


class EventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, event_id: int) -> Event | None:
        result = await self._session.execute(select(Event).where(Event.id == event_id))
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(self, key: uuid.UUID) -> Event | None:
        result = await self._session.execute(
            select(Event).where(Event.idempotency_key == key)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        user_id: int,
        title: str,
        start_at: datetime,
        end_at: datetime | None = None,
    ) -> Event:
        event = Event(
            user_id=user_id,
            title=title,
            start_at=start_at,
            end_at=end_at,
            status="pending",
            idempotency_key=uuid.uuid4(),
        )
        self._session.add(event)
        await self._session.flush()
        await self._session.refresh(event)
        return event

    async def update_status(
        self,
        event_id: int,
        status: str,
        external_id: str | None = None,
        last_error: str | None = None,
    ) -> Event | None:
        event = await self.get_by_id(event_id)
        if event is None:
            return None
        event.status = status
        if external_id is not None:
            event.external_id = external_id
        if last_error is not None:
            event.last_error = last_error
        await self._session.flush()
        return event

    async def increment_retry(self, event_id: int, error: str) -> Event | None:
        event = await self.get_by_id(event_id)
        if event is None:
            return None
        event.retry_count += 1
        event.last_error = error
        await self._session.flush()
        return event

    async def get_pending_for_retry(self, older_than_seconds: int = 60) -> list[Event]:
        cutoff = datetime.now(UTC) - timedelta(seconds=older_than_seconds)
        result = await self._session.execute(
            select(Event).where(
                Event.status == "confirmed",
                Event.created_at <= cutoff,
            )
        )
        return list(result.scalars().all())

    async def list_upcoming(self, user_id: int, count: int = 5) -> list[Event]:
        now = datetime.now(UTC)
        result = await self._session.execute(
            select(Event)
            .where(
                Event.user_id == user_id,
                Event.status == "synced",
                Event.start_at >= now,
            )
            .order_by(Event.start_at)
            .limit(count)
        )
        return list(result.scalars().all())
