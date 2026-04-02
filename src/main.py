import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.api.health import router as health_router
from src.api.oauth_callback import router as oauth_router
from src.api.webhook import router as webhook_router
from src.bot.setup import bot
from src.config import settings
from src.logging_config import configure_logging
from src.tasks.scheduler import create_scheduler

# Configure structlog before any log calls are made.
configure_logging()

logger = structlog.get_logger(__name__)

_start_time: float = 0.0


def _init_sentry() -> None:
    if not settings.sentry_dsn:
        return
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env.value,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        traces_sample_rate=0.1,
    )
    logger.info("sentry_initialised")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    global _start_time  # noqa: PLW0603
    _start_time = time.monotonic()

    _init_sentry()

    scheduler = create_scheduler()
    scheduler.start()
    logger.info("scheduler_started")

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        logger.info("scheduler_stopped")
        await bot.session.close()


def get_uptime() -> float:
    return time.monotonic() - _start_time


app = FastAPI(
    title="Telegram Calendar Bot",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(oauth_router)
app.include_router(webhook_router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        exc_info=exc,
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
