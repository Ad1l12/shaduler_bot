# Промт для Claude Code

Ты — Senior Backend Developer. Твоя задача — создать проект с нуля на основе README.md в корне репозитория.

## Контекст

README.md содержит полную документацию проекта: архитектуру, стек, структуру файлов, схему БД, конфигурацию. Прочитай его целиком перед началом работы — это твой единственный источник правды.

## Порядок работы

Реализуй проект **строго поэтапно**. После каждого этапа — убедись, что код запускается, линтер проходит, тесты проходят. Не переходи к следующему этапу, пока текущий не работает.

### Этап 1: Скелет проекта

1. Создай структуру директорий как в README (src/, tests/, deploy/, alembic/).
2. Создай `pyproject.toml` со всеми зависимостями из README (основные + dev). Используй формат `[project]` + `[project.optional-dependencies]` для dev-зависимостей.
3. Создай `.env.example` со всеми переменными из README.
4. Создай `src/config.py` — Pydantic Settings, загрузка из .env.
5. Создай `src/main.py` — минимальное FastAPI-приложение с endpoint `/health`.
6. Создай `Dockerfile` и `deploy/docker-compose.dev.yml`.
7. Создай `.pre-commit-config.yaml`, `.gitignore`, `LICENSE` (MIT).
8. **Проверка:** `ruff check src/` и `mypy src/` проходят без ошибок.

### Этап 2: База данных

1. Создай SQLAlchemy 2.x async-модели в `src/models/`:
   - `user.py` — таблица users (id, telegram_id BIGINT UNIQUE, timezone VARCHAR DEFAULT 'UTC', created_at, updated_at)
   - `oauth_credential.py` — таблица oauth_credentials (id, user_id FK, provider ENUM('google'), encrypted_refresh_token BYTEA, encrypted_access_token BYTEA, token_expires_at TIMESTAMP, calendar_id VARCHAR, created_at, updated_at)
   - `event.py` — таблица events (id, user_id FK, title VARCHAR(200), start_at TIMESTAMP WITH TZ, end_at TIMESTAMP WITH TZ NULLABLE, status ENUM('pending','confirmed','synced','failed'), external_id VARCHAR NULLABLE, idempotency_key UUID UNIQUE, retry_count INT DEFAULT 0, last_error TEXT NULLABLE, created_at)
2. Создай `src/db/session.py` — async engine + AsyncSession factory через asyncpg.
3. Настрой Alembic (`alembic.ini`, `alembic/env.py`) для async.
4. Сгенерируй начальную миграцию.
5. Создай `src/db/repositories/` — user_repo.py, event_repo.py с базовыми CRUD-операциями (async).
6. **Проверка:** миграция применяется к тестовой БД без ошибок.

### Этап 3: Безопасность

1. Создай `src/security/encryption.py` — Fernet-шифрование/расшифровка токенов. Две функции: `encrypt_token(plaintext: str) -> bytes` и `decrypt_token(ciphertext: bytes) -> str`. Ключ из config.
2. Создай `src/security/webhook_verify.py` — middleware или dependency для проверки заголовка `X-Telegram-Bot-Api-Secret-Token`.
3. Напиши тесты: `tests/unit/test_encryption.py` — шифрование/расшифровка, невалидный ключ, пустая строка.
4. **Проверка:** `pytest tests/unit/test_encryption.py` — зелёный.

### Этап 4: Parser Service

1. Создай `src/services/parser_service.py`:
   - Функция `parse_message(text: str, timezone: str, now: datetime) -> ParsedEvent | None`
   - Чистая функция без side-effects
   - Используй `dateparser` для извлечения даты/времени (настрой на русский язык)
   - Всё, что не распознано как дата — это title
   - Валидация через Pydantic: title max 200 chars, datetime не в прошлом
2. Создай `src/schemas/parsed_message.py` — Pydantic-модель ParsedEvent (title: str, start_at: datetime, end_at: datetime | None).
3. Напиши тесты `tests/unit/test_parser_service.py` — минимум 15 кейсов:
   - "завтра в 18 тренировка"
   - "в пятницу в 20 ужин с друзьями"
   - "послезавтра стоматолог"
   - "через 2 часа созвон"
   - "15 мая в 10:30 собеседование"
   - "сегодня вечером йога"
   - Пустая строка → None
   - "привет" (нет даты) → None
   - Очень длинный текст (>512 символов) → обрезка/None
   - Дата в прошлом → None
4. **Проверка:** `pytest tests/unit/test_parser_service.py` — все тесты зелёные.

### Этап 5: Auth Service (Google OAuth)

1. Создай `src/services/auth_service.py`:
   - `generate_auth_url(user_id: int) -> str` — формирует OAuth URL с state=user_id
   - `handle_callback(code: str, state: str) -> bool` — обменивает code на токены, шифрует, сохраняет в БД
   - `get_valid_token(user_id: int) -> str | None` — возвращает access_token, обновляя через refresh_token если истёк
   - `revoke_access(user_id: int) -> None` — удаляет токены из БД
2. Используй `google-auth` и `google-auth-oauthlib`. НЕ используй устаревший `oauth2client`.
3. При 401 от Google после refresh — помечай credentials как невалидные.
4. Создай `src/api/oauth_callback.py` — GET `/auth/google/callback`.

### Этап 6: Calendar Service

1. Создай `src/services/calendar_service.py`:
   - `create_event(access_token: str, calendar_id: str, event_data: ParsedEvent, idempotency_key: str) -> str` — создаёт событие, возвращает google event id
   - `list_upcoming(access_token: str, calendar_id: str, count: int = 5) -> list` — предстоящие события
   - `delete_event(access_token: str, calendar_id: str, event_id: str) -> bool`
   - `check_conflicts(access_token: str, calendar_id: str, start: datetime, end: datetime) -> list` — проверка пересечений
2. Retry-логика через `tenacity`: 3 попытки, exponential backoff, retry на 429/503/timeout.
3. Idempotency: передавай `idempotency_key` как поле `id` события в Google Calendar API (формат: lowercase alphanumeric, 5-1024 символов).

### Этап 7: Event Service

1. Создай `src/services/event_service.py` — оркестрация:
   - `create_pending_event(user_id: int, parsed: ParsedEvent) -> Event` — сохраняет в БД со статусом pending
   - `confirm_event(event_id: int) -> Event` — меняет статус на confirmed
   - `sync_event(event_id: int) -> Event` — отправляет в Google Calendar, ставит synced/failed
   - `get_pending_events_for_retry() -> list[Event]` — события confirmed старше 60 секунд
2. Создай `src/services/user_service.py` — CRUD пользователей.

### Этап 8: Telegram Bot

1. Создай `src/bot/handlers/`:
   - `start.py` — /start, /help
   - `connect.py` — /connect (отправляет OAuth URL), /disconnect (удаляет токены)
   - `events.py` — обработка текстовых сообщений (парсинг → превью → inline-кнопка "Создать")
   - `callbacks.py` — обработка нажатия inline-кнопки подтверждения → sync_event
2. Создай `src/bot/keyboards.py` — inline-клавиатуры (подтверждение, отмена).
3. Создай `src/bot/middlewares.py` — rate limiting (10 msg/min на user), логирование.
4. Зарегистрируй aiogram Router в FastAPI через webhook endpoint.
5. Создай `src/api/webhook.py` — POST `/webhook/telegram` с проверкой secret token.

### Этап 9: Фоновые задачи

1. Создай `src/tasks/scheduler.py` — APScheduler setup, запуск при старте FastAPI (lifespan).
2. Создай `src/tasks/retry_pending.py` — задача каждые 60 секунд: найти confirmed события без sync, повторить отправку.
3. Создай `src/tasks/refresh_tokens.py` — задача каждые 30 минут: найти токены с token_expires_at < now + 5 min, обновить.

### Этап 10: Logging и мониторинг

1. Настрой structlog в `src/main.py` — JSON-формат, вывод в stdout.
2. Добавь structured-логирование во все сервисы (event_created, event_synced, token_refreshed, parse_failed и т.д.).
3. Подключи sentry-sdk в `src/main.py` (опционально, если SENTRY_DSN задан).
4. Расширь `/health` — проверка соединения с PostgreSQL.

### Этап 11: Интеграционные тесты

1. Создай `tests/conftest.py`:
   - Фикстура: тестовая async БД (создание/удаление таблиц)
   - Фикстура: FastAPI TestClient
   - Фикстура: мок Google API (httpx mock или responses)
2. Создай `tests/integration/test_webhook_flow.py`:
   - Полный цикл: webhook с текстом → парсинг → pending event в БД → callback подтверждения → confirmed
3. Создай `tests/integration/test_oauth_flow.py`:
   - OAuth callback с мок-кодом → токены сохранены в БД зашифровано

### Этап 12: CI/CD и деплой

1. Создай `.github/workflows/ci.yml` — lint + тесты на каждый PR (содержимое есть в README).
2. Создай `.github/workflows/deploy.yml` — деплой на VPS при мерже в main.
3. Создай `deploy/docker-compose.yml` (продакшен) и `deploy/nginx/bot.conf`.
4. Создай `deploy/init-letsencrypt.sh`.

## Принципы кода

- **Async everywhere:** все I/O операции — async/await (asyncpg, httpx/aiohttp, aiogram).
- **Типизация:** все функции с type hints, mypy strict mode.
- **Pydantic v2:** для всех схем, конфигов, валидации.
- **Repository pattern:** вся работа с БД через репозитории, сервисы не знают о SQLAlchemy.
- **Dependency Injection:** через FastAPI Depends для сессий БД, сервисов.
- **Никаких print():** только structlog.
- **Секреты:** никогда не логировать токены, пароли, ключи. Фильтровать в structlog-процессоре.
- **Graceful shutdown:** FastAPI lifespan — остановка scheduler, ожидание текущих задач.
- **Валидация на входе:** все данные от Telegram и Google проходят через Pydantic-схемы.
- **Ошибки:** кастомные exception-классы (TokenExpiredError, ParseError, GoogleApiError), глобальный exception handler в FastAPI.

## Чего НЕ делать

- Не используй `oauth2client` — он deprecated. Только `google-auth`.
- Не используй `python-telegram-bot` — используй `aiogram 3.x`.
- Не используй sync-драйверы БД (psycopg2). Только `asyncpg`.
- Не храни токены в plaintext — всегда шифруй.
- Не делай `from dotenv import load_dotenv` в коде — Pydantic Settings сам читает .env.
- Не создавай микросервисы — всё в одном приложении.
- Не добавляй Redis, Celery, Kafka — это MVP.
- Не пиши `# TODO` без issue — если что-то не реализуешь, не упоминай.