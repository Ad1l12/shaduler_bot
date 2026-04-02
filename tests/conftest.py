"""Root conftest — shared fixtures for integration tests.

pytest_configure runs before any test module is imported, so env vars are in
place before src.config.Settings() is instantiated during collection.

DB strategy
-----------
Integration tests use SQLite in-memory via aiosqlite.  All PostgreSQL-specific
types (UUID, Enum, BYTEA, DateTime(timezone=True)) work transparently under
SQLite for the operations we need.  This means tests run without a running
Postgres instance.

The ``db_session`` fixture creates all tables fresh for each test function and
drops them on teardown, giving full isolation without a test database server.

Google API mock
---------------
``mock_calendar_service`` patches the entire ``src.services.calendar_service``
module at the function-call level, so no HTTP requests are ever made to
Google.  All integration tests that exercise the sync path must use this
fixture (directly or indirectly).
"""

import os
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.models.base import Base


def pytest_configure(config: pytest.Config) -> None:
    """Populate required env vars so Settings() can be instantiated in tests."""
    from cryptography.fernet import Fernet

    os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456789:AAtest-token-for-pytest")
    os.environ.setdefault("TELEGRAM_WEBHOOK_SECRET", "test-webhook-secret")
    os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-client-secret")
    os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())


# ── In-memory SQLite engine (module-scoped so it is created once per session) ─

_TEST_DB_URL = "sqlite+aiosqlite://"

_test_engine = create_async_engine(_TEST_DB_URL, echo=False)
_TestSessionFactory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    _test_engine, expire_on_commit=False
)


@pytest_asyncio.fixture(autouse=False)
async def db_session() -> AsyncIterator[AsyncSession]:
    """Create all tables, yield a session, then drop all tables.

    Each test gets a completely clean schema.  We import all model modules
    here so SQLAlchemy's metadata is fully populated before create_all().
    """
    # Ensure all models are registered in Base.metadata
    import src.models.event  # noqa: F401
    import src.models.oauth_credential  # noqa: F401
    import src.models.user  # noqa: F401

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with _TestSessionFactory() as session:
        yield session

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(autouse=False)
async def http_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """Return an httpx AsyncClient wired to the FastAPI app.

    The DB session middleware is overridden so every request uses the same
    ``db_session`` fixture session.  This makes assertions about DB state
    straightforward: after a request, the test can query ``db_session``
    directly without a separate connection.
    """
    from src.db.session import get_session
    from src.main import app

    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session

    # Patch DbSessionMiddleware so it also uses the fixture session instead of
    # opening a new one from AsyncSessionFactory.
    async def _patched_middleware_call(
        self: Any,
        handler: Any,
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        data["session"] = db_session
        result = await handler(event, data)
        return result

    with patch(
        "src.bot.middlewares.DbSessionMiddleware.__call__",
        new=_patched_middleware_call,
    ):
        transport = ASGITransport(app=app)  # type: ignore[arg-type]
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

    app.dependency_overrides.clear()


@pytest.fixture()
def mock_calendar_service() -> AsyncIterator[dict[str, AsyncMock]]:
    """Patch all Google Calendar API functions with AsyncMocks.

    Returns a dict of mock objects so tests can configure return values and
    assert call counts/arguments.

    This fixture MUST be used for every test that exercises the sync path.
    No real HTTP calls are ever made to Google.
    """
    mocks = {
        "create_event": AsyncMock(return_value="googleeventid123"),
        "list_upcoming": AsyncMock(return_value=[]),
        "delete_event": AsyncMock(return_value=True),
        "check_conflicts": AsyncMock(return_value=[]),
    }
    with (
        patch("src.services.calendar_service.create_event", mocks["create_event"]),
        patch("src.services.calendar_service.list_upcoming", mocks["list_upcoming"]),
        patch("src.services.calendar_service.delete_event", mocks["delete_event"]),
        patch("src.services.calendar_service.check_conflicts", mocks["check_conflicts"]),
        # Also patch inside event_service's import alias
        patch("src.services.event_service.calendar_service.create_event", mocks["create_event"]),
    ):
        yield mocks
