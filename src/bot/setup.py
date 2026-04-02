"""Bot and Dispatcher singletons.

Import ``bot`` and ``dp`` from here everywhere they are needed.
All middlewares and routers are registered once at module load time.
"""

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from src.bot.handlers import callbacks, connect, events, start
from src.bot.middlewares import DbSessionMiddleware, RateLimitMiddleware
from src.config import settings

# ── Bot ──────────────────────────────────────────────────────────────────────

bot = Bot(
    token=settings.telegram_bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)

# ── Dispatcher ───────────────────────────────────────────────────────────────

dp = Dispatcher()

# Rate limiting applies only to incoming messages (not callback queries).
# It is registered before DbSessionMiddleware so that rate-limited requests
# never open a DB session.
dp.message.middleware(RateLimitMiddleware(limit=10, window=60))

# DB session is injected for both message and callback-query handlers.
dp.message.middleware(DbSessionMiddleware())
dp.callback_query.middleware(DbSessionMiddleware())

# ── Routers (order matters: more specific first) ──────────────────────────────

dp.include_router(start.router)      # /start, /help
dp.include_router(connect.router)    # /connect, /disconnect
dp.include_router(events.router)     # /list, /timezone, text messages
dp.include_router(callbacks.router)  # inline-button callbacks
