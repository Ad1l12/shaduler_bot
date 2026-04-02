from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import settings

engine = create_async_engine(
    settings.database_url,
    pool_size=5,
    max_overflow=10,
    echo=False,
)

AsyncSessionFactory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    expire_on_commit=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionFactory() as session:
        yield session
