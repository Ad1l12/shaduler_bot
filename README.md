# 📅 Telegram → Google Calendar Assistant

Telegram-бот, который создаёт события в Google Calendar из обычного текста.

Напиши боту `завтра в 18 тренировка` — и событие появится в твоём календаре.

---

## Оглавление

- [Обзор проекта](#обзор-проекта)
- [Стек технологий](#стек-технологий)
- [Архитектура](#архитектура)
- [Структура проекта](#структура-проекта)
- [Требования](#требования)
- [Быстрый старт (локально)](#быстрый-старт-локально)
- [Конфигурация](#конфигурация)
- [Настройка внешних сервисов](#настройка-внешних-сервисов)
- [Работа с базой данных](#работа-с-базой-данных)
- [Тестирование](#тестирование)
- [Деплой на продакшен](#деплой-на-продакшен)
- [CI/CD](#cicd)
- [Мониторинг и логирование](#мониторинг-и-логирование)
- [API Reference](#api-reference)
- [Troubleshooting](#troubleshooting)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [Лицензия](#лицензия)

---

## Обзор проекта

### Что делает бот

1. Пользователь подключает Google Calendar через команду `/connect`
2. Пишет сообщение в свободной форме: `в пятницу в 20 ужин с друзьями`
3. Бот распознаёт дату, время и название события
4. Показывает превью и кнопку подтверждения
5. Создаёт событие в Google Calendar

### Пользовательские команды

| Команда      | Описание                                      |
|-------------|-----------------------------------------------|
| `/start`    | Приветствие и инструкция                       |
| `/connect`  | Подключение Google аккаунта через OAuth        |
| `/disconnect` | Отключение Google аккаунта и удаление токенов |
| `/list`     | Последние 5 предстоящих событий                |
| `/timezone` | Установка часового пояса                       |
| `/help`     | Справка по использованию                       |

---

## Стек технологий

### Backend (ядро)

| Технология         | Версия   | Назначение                                                    |
|-------------------|----------|---------------------------------------------------------------|
| **Python**        | 3.12+    | Основной язык                                                  |
| **FastAPI**       | 0.115+   | HTTP-фреймворк (webhook endpoint, OAuth callback, healthcheck) |
| **Uvicorn**       | 0.30+    | ASGI-сервер                                                    |
| **Pydantic**      | 2.x      | Валидация данных, settings, схемы                              |

### Telegram

| Технология               | Назначение                                        |
|--------------------------|---------------------------------------------------|
| **aiogram**  3.x         | Асинхронный Telegram Bot фреймворк                |
| **Telegram Bot API**     | Webhook-режим (не polling) для продакшена         |

### Google интеграция

| Технология                          | Назначение                              |
|------------------------------------|-----------------------------------------|
| **google-auth** + **google-auth-oauthlib** | OAuth 2.0 авторизация              |
| **google-api-python-client**       | Google Calendar API v3                   |

### Парсинг естественного языка

| Технология      | Назначение                                                     |
|----------------|----------------------------------------------------------------|
| **dateparser**  | Извлечение даты и времени из русского текста                    |

> На следующем этапе — замена на LLM (Claude API) для сложных случаев с fallback на dateparser.

### База данных

| Технология          | Назначение                                               |
|--------------------|----------------------------------------------------------|
| **PostgreSQL** 16   | Основное хранилище                                        |
| **asyncpg**         | Асинхронный драйвер PostgreSQL                            |
| **SQLAlchemy** 2.x  | ORM (async-режим)                                         |
| **Alembic**         | Миграции БД                                               |

### Безопасность

| Технология               | Назначение                                   |
|--------------------------|----------------------------------------------|
| **cryptography** (Fernet) | AES-шифрование OAuth-токенов at rest          |
| **python-dotenv**         | Управление секретами через .env               |

### Инфраструктура

| Технология           | Назначение                              |
|---------------------|-----------------------------------------|
| **Docker**           | Контейнеризация приложения               |
| **docker-compose**   | Оркестрация контейнеров (app + postgres) |
| **Nginx**            | Reverse proxy, SSL termination           |
| **Certbot**          | Let's Encrypt SSL-сертификаты            |

### Качество кода и тесты

| Технология   | Назначение                            |
|-------------|---------------------------------------|
| **pytest**   | Тестовый фреймворк                     |
| **pytest-asyncio** | Тестирование async-кода          |
| **coverage** | Покрытие тестами                       |
| **ruff**     | Линтер + форматтер (замена flake8+black+isort) |
| **mypy**     | Статическая типизация                  |
| **pre-commit** | Git-хуки для проверок перед коммитом |

### Логирование и мониторинг

| Технология    | Назначение                             |
|--------------|----------------------------------------|
| **structlog** | Структурированные логи в JSON          |
| **sentry-sdk** | Отслеживание ошибок в продакшене     |

---

## Архитектура

Проект построен как **модульный монолит** — все сервисы внутри одного приложения, но с чётким разделением ответственности.

```
┌─────────────────────────────────────────────────────────┐
│                    FastAPI Application                   │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌────────────────────────┐ │
│  │ Telegram  │  │  OAuth   │  │    Health / Metrics    │ │
│  │ Webhook   │  │ Callback │  │      Endpoints         │ │
│  └─────┬─────┘  └────┬─────┘  └────────────────────────┘ │
│        │              │                                   │
│  ┌─────▼──────────────▼─────────────────────────────────┐ │
│  │                  Core Services                        │ │
│  │                                                       │ │
│  │  ┌────────────┐ ┌────────────┐ ┌───────────────────┐ │ │
│  │  │  Auth      │ │  Parser    │ │  Calendar          │ │ │
│  │  │  Service   │ │  Service   │ │  Service           │ │ │
│  │  └────────────┘ └────────────┘ └───────────────────┘ │ │
│  │  ┌────────────┐ ┌────────────┐                       │ │
│  │  │  User      │ │  Event     │                       │ │
│  │  │  Service   │ │  Service   │                       │ │
│  │  └────────────┘ └────────────┘                       │ │
│  └───────────────────┬───────────────────────────────────┘ │
│                      │                                     │
│  ┌───────────────────▼───────────────────────────────────┐ │
│  │              Data Layer (SQLAlchemy + asyncpg)         │ │
│  └───────────────────┬───────────────────────────────────┘ │
└──────────────────────┼──────────────────────────────────────┘
                       │
              ┌────────▼────────┐
              │   PostgreSQL    │
              └─────────────────┘
```

### Потоки данных

**Создание события:**

```
Telegram → Webhook Handler → Parser Service → Event Service (status: pending)
    → Inline-кнопка "Подтвердить" → Event Service (status: confirmed)
    → Calendar Service → Google Calendar API → Event Service (status: synced)
```

**Авторизация:**

```
/connect → Auth Service → Google OAuth consent screen
    → OAuth callback → Auth Service → сохранение токенов в БД (зашифровано)
```

---

## Структура проекта

```
telegram-calendar-bot/
├── .github/
│   └── workflows/
│       ├── ci.yml                  # Линтинг + тесты на каждый PR
│       └── deploy.yml              # Деплой на VPS при мерже в main
│
├── alembic/
│   ├── versions/                   # Файлы миграций
│   ├── env.py
│   └── alembic.ini
│
├── src/
│   ├── __init__.py
│   ├── main.py                     # Точка входа FastAPI
│   ├── config.py                   # Pydantic Settings (из .env)
│   │
│   ├── api/                        # HTTP-слой
│   │   ├── __init__.py
│   │   ├── webhook.py              # POST /webhook/telegram
│   │   ├── oauth_callback.py       # GET /auth/google/callback
│   │   └── health.py               # GET /health
│   │
│   ├── bot/                        # Telegram-логика
│   │   ├── __init__.py
│   │   ├── handlers/
│   │   │   ├── __init__.py
│   │   │   ├── start.py            # /start, /help
│   │   │   ├── connect.py          # /connect, /disconnect
│   │   │   ├── events.py           # /list, обработка текста
│   │   │   └── callbacks.py        # Inline-кнопки (подтверждение)
│   │   ├── keyboards.py            # Inline-клавиатуры
│   │   └── middlewares.py          # Rate limiting, логирование
│   │
│   ├── services/                   # Бизнес-логика
│   │   ├── __init__.py
│   │   ├── auth_service.py         # OAuth flow, токены
│   │   ├── parser_service.py       # Текст → структурированные данные
│   │   ├── calendar_service.py     # Google Calendar API
│   │   ├── event_service.py        # CRUD событий, retry-логика
│   │   └── user_service.py         # CRUD пользователей
│   │
│   ├── models/                     # SQLAlchemy-модели
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── oauth_credential.py
│   │   └── event.py
│   │
│   ├── schemas/                    # Pydantic-схемы
│   │   ├── __init__.py
│   │   ├── event.py
│   │   └── parsed_message.py
│   │
│   ├── db/                         # Работа с БД
│   │   ├── __init__.py
│   │   ├── session.py              # AsyncSession factory
│   │   └── repositories/           # Паттерн Repository
│   │       ├── __init__.py
│   │       ├── user_repo.py
│   │       └── event_repo.py
│   │
│   ├── security/                   # Шифрование, валидация
│   │   ├── __init__.py
│   │   ├── encryption.py           # Fernet encrypt/decrypt токенов
│   │   └── webhook_verify.py       # Проверка Telegram secret token
│   │
│   └── tasks/                      # Фоновые задачи
│       ├── __init__.py
│       ├── scheduler.py            # APScheduler setup
│       ├── retry_pending.py        # Повторная отправка зависших событий
│       └── refresh_tokens.py       # Проактивное обновление токенов
│
├── tests/
│   ├── conftest.py                 # Фикстуры (test DB, mock Google API)
│   ├── unit/
│   │   ├── test_parser_service.py  # 50+ кейсов парсинга
│   │   ├── test_encryption.py
│   │   └── test_event_service.py
│   ├── integration/
│   │   ├── test_webhook_flow.py    # Полный flow: сообщение → событие
│   │   └── test_oauth_flow.py
│   └── fixtures/
│       └── google_api_responses.py # Моки ответов Google API
│
├── deploy/
│   ├── nginx/
│   │   └── bot.conf                # Nginx конфиг
│   ├── docker-compose.yml          # Продакшен-композиция
│   ├── docker-compose.dev.yml      # Dev-композиция (hot reload)
│   └── init-letsencrypt.sh         # Скрипт получения SSL-сертификата
│
├── Dockerfile
├── .env.example                    # Шаблон переменных окружения
├── .pre-commit-config.yaml
├── pyproject.toml                  # Зависимости, настройки ruff/mypy/pytest
├── README.md
└── LICENSE
```

---

## Требования

- Python 3.12+
- PostgreSQL 16+
- Docker и Docker Compose (для контейнерного запуска)
- Telegram Bot Token (от @BotFather)
- Google Cloud проект с включённым Calendar API
- VPS с публичным IP и доменом (для продакшена)

---

## Быстрый старт (локально)

### 1. Клонирование репозитория

```bash
git clone https://github.com/<your-username>/telegram-calendar-bot.git
cd telegram-calendar-bot
```

### 2. Создание виртуального окружения

```bash
python3.12 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows
```

### 3. Установка зависимостей

```bash
pip install -e ".[dev]"
```

### 4. Настройка переменных окружения

```bash
cp .env.example .env
# Отредактируйте .env — заполните все обязательные переменные (см. раздел Конфигурация)
```

### 5. Запуск PostgreSQL

```bash
# Через Docker (рекомендуется):
docker run -d \
  --name calendar-bot-db \
  -e POSTGRES_DB=calendar_bot \
  -e POSTGRES_USER=bot \
  -e POSTGRES_PASSWORD=localpass \
  -p 5432:5432 \
  postgres:16-alpine
```

### 6. Применение миграций

```bash
alembic upgrade head
```

### 7. Запуск приложения (dev-режим)

```bash
# Через Uvicorn с hot reload:
uvicorn src.main:app --reload --port 8000

# Или через Docker Compose (app + postgres):
docker compose -f deploy/docker-compose.dev.yml up
```

### 8. Проброс webhook для локальной разработки

Telegram требует публичный HTTPS URL для webhook. Для локальной разработки используйте ngrok:

```bash
# Установка: https://ngrok.com/download
ngrok http 8000

# ngrok выдаст URL вида https://abc123.ngrok-free.app
# Установите webhook:
curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://abc123.ngrok-free.app/webhook/telegram", "secret_token": "<WEBHOOK_SECRET>"}'
```

---

## Конфигурация

Все настройки загружаются из переменных окружения через Pydantic Settings. Шаблон в `.env.example`:

```ini
# ── Приложение ──────────────────────────────────────
APP_ENV=development              # development | production
APP_LOG_LEVEL=DEBUG              # DEBUG | INFO | WARNING | ERROR
APP_BASE_URL=https://your-domain.com  # Публичный URL (для OAuth callback)

# ── Telegram ────────────────────────────────────────
TELEGRAM_BOT_TOKEN=123456:ABC-DEF     # Токен от @BotFather
TELEGRAM_WEBHOOK_SECRET=your-random-secret-string  # Для верификации webhook

# ── Google OAuth ────────────────────────────────────
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxx
GOOGLE_REDIRECT_URI=${APP_BASE_URL}/auth/google/callback

# ── База данных ─────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://bot:localpass@localhost:5432/calendar_bot

# ── Шифрование ──────────────────────────────────────
ENCRYPTION_KEY=your-fernet-key        # Генерация: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# ── Sentry (опционально, для продакшена) ────────────
SENTRY_DSN=https://xxx@sentry.io/xxx
```

### Генерация секретов

```bash
# Fernet-ключ для шифрования токенов:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Случайная строка для webhook secret:
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## Настройка внешних сервисов

### Telegram Bot

1. Откройте @BotFather в Telegram
2. Отправьте `/newbot`, следуйте инструкциям
3. Скопируйте токен в `TELEGRAM_BOT_TOKEN`
4. Через `/setcommands` задайте список команд:
   ```
   start - Начать работу с ботом
   connect - Подключить Google Calendar
   disconnect - Отключить Google Calendar
   list - Показать предстоящие события
   timezone - Установить часовой пояс
   help - Справка
   ```

### Google Cloud Project

1. Перейдите в [Google Cloud Console](https://console.cloud.google.com/)
2. Создайте новый проект
3. Включите **Google Calendar API** (APIs & Services → Library)
4. Создайте **OAuth 2.0 credentials** (APIs & Services → Credentials):
   - Application type: Web application
   - Authorized redirect URIs: `https://your-domain.com/auth/google/callback`
5. Скопируйте Client ID и Client Secret в `.env`
6. Настройте **OAuth consent screen**:
   - User type: External
   - Scopes: `https://www.googleapis.com/auth/calendar.events`
   - Добавьте тестовых пользователей (до прохождения верификации — лимит 100 пользователей)

> **Важно:** Для выхода за лимит 100 пользователей необходимо пройти верификацию Google OAuth — процесс занимает 2–6 недель. Начните заранее. Потребуется: privacy policy, terms of service, домен, демо-видео работы приложения.

---

## Работа с базой данных

### Схема

```
┌──────────────────┐     ┌───────────────────────┐     ┌──────────────────────┐
│     users        │     │  oauth_credentials    │     │       events         │
├──────────────────┤     ├───────────────────────┤     ├──────────────────────┤
│ id           PK  │◄──┐ │ id                PK  │     │ id               PK  │
│ telegram_id  UQ  │   └─│ user_id           FK  │  ┌──│ user_id          FK  │
│ timezone         │     │ provider  ENUM        │  │  │ title                │
│ created_at       │     │ encrypted_refresh     │  │  │ start_at             │
│ updated_at       │     │ encrypted_access      │  │  │ end_at               │
└──────────────────┘     │ token_expires_at      │  │  │ status     ENUM      │
                         │ calendar_id           │  │  │ external_id          │
                         │ created_at            │  │  │ idempotency_key  UQ  │
                         └───────────────────────┘  │  │ retry_count          │
                                                    │  │ last_error           │
                              ┌──────────────────┐  │  │ created_at           │
                              │     users        │──┘  └──────────────────────┘
                              └──────────────────┘

status ENUM: pending → confirmed → synced | failed
```

### Миграции

```bash
# Создать новую миграцию после изменения моделей:
alembic revision --autogenerate -m "описание изменения"

# Применить все миграции:
alembic upgrade head

# Откатить последнюю миграцию:
alembic downgrade -1

# Посмотреть текущую версию:
alembic current

# Посмотреть историю миграций:
alembic history
```

---

## Тестирование

### Структура тестов

```
tests/
├── unit/                    # Быстрые, без внешних зависимостей
│   ├── test_parser_service  # Парсинг текста → дата + название
│   ├── test_encryption      # Шифрование/расшифровка токенов
│   └── test_event_service   # Бизнес-логика событий
├── integration/             # С тестовой БД и моками Google API
│   ├── test_webhook_flow    # Полный цикл: сообщение → событие в БД
│   └── test_oauth_flow      # OAuth flow с мок-сервером Google
└── fixtures/                # Моки ответов внешних API
```

### Запуск тестов

```bash
# Все тесты:
pytest

# Только unit-тесты (быстро, без БД):
pytest tests/unit/

# С покрытием:
pytest --cov=src --cov-report=html
# Отчёт: htmlcov/index.html

# Конкретный файл:
pytest tests/unit/test_parser_service.py -v

# Конкретный тест:
pytest tests/unit/test_parser_service.py::test_tomorrow_evening -v
```

### Тестовая БД

Интеграционные тесты используют отдельную PostgreSQL базу. Настройка в `conftest.py`:

```bash
# Запустите тестовую БД:
docker run -d \
  --name calendar-bot-test-db \
  -e POSTGRES_DB=calendar_bot_test \
  -e POSTGRES_USER=bot \
  -e POSTGRES_PASSWORD=testpass \
  -p 5433:5432 \
  postgres:16-alpine

# Задайте переменную:
export TEST_DATABASE_URL=postgresql+asyncpg://bot:testpass@localhost:5433/calendar_bot_test
```

### Что обязательно покрыть тестами

**Parser Service (приоритет №1)** — это самый хрупкий компонент. Минимальный набор кейсов:

```
"завтра в 18 тренировка"         → 2026-04-03T18:00, "тренировка"
"в пятницу в 20 ужин с друзьями" → ближайшая пятница 20:00, "ужин с друзьями"
"послезавтра стоматолог"         → 2026-04-04T09:00 (default time), "стоматолог"
"через 2 часа созвон"            → now + 2h, "созвон"
"15 мая в 10:30 собеседование"   → 2026-05-15T10:30, "собеседование"
"сегодня вечером йога"           → today 19:00, "йога"
""                               → None (пустое сообщение)
"привет"                         → None (нет даты)
"в 25:00 тест"                   → None (невалидное время)
```

### Линтинг и форматирование

```bash
# Проверка (CI):
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/

# Автоисправление:
ruff check --fix src/ tests/
ruff format src/ tests/
```

### Pre-commit хуки

```bash
# Установка:
pre-commit install

# Ручной запуск по всем файлам:
pre-commit run --all-files
```

Конфигурация `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.13.0
    hooks:
      - id: mypy
        additional_dependencies: [pydantic>=2.0]
```

---

## Деплой на продакшен

### Требования к серверу

- VPS: 1 vCPU, 2 GB RAM, 20 GB SSD (достаточно для старта; Hetzner CX22 — ~€4/мес)
- ОС: Ubuntu 24.04 LTS
- Домен, направленный A-записью на IP сервера

### Шаг 1: Подготовка сервера

```bash
# Подключение по SSH:
ssh root@your-server-ip

# Обновление системы:
apt update && apt upgrade -y

# Установка Docker:
curl -fsSL https://get.docker.com | sh

# Установка Docker Compose:
apt install docker-compose-plugin -y

# Создание пользователя (не работаем от root):
adduser deploy
usermod -aG docker deploy
su - deploy
```

### Шаг 2: Клонирование и настройка

```bash
git clone https://github.com/<your-username>/telegram-calendar-bot.git
cd telegram-calendar-bot

# Создание .env из шаблона:
cp .env.example .env
nano .env  # Заполните все переменные для продакшена
```

### Шаг 3: SSL-сертификат

```bash
# Первоначальное получение сертификата:
chmod +x deploy/init-letsencrypt.sh
sudo ./deploy/init-letsencrypt.sh
```

### Шаг 4: Запуск

```bash
docker compose -f deploy/docker-compose.yml up -d
```

### Шаг 5: Применение миграций

```bash
docker compose -f deploy/docker-compose.yml exec app alembic upgrade head
```

### Шаг 6: Установка Telegram Webhook

```bash
curl -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-domain.com/webhook/telegram",
    "secret_token": "'"${TELEGRAM_WEBHOOK_SECRET}"'",
    "max_connections": 40,
    "allowed_updates": ["message", "callback_query"]
  }'
```

### Шаг 7: Проверка

```bash
# Healthcheck:
curl https://your-domain.com/health

# Логи:
docker compose -f deploy/docker-compose.yml logs -f app

# Статус контейнеров:
docker compose -f deploy/docker-compose.yml ps
```

### Docker Compose (продакшен)

```yaml
# deploy/docker-compose.yml
services:
  app:
    build:
      context: ..
      dockerfile: Dockerfile
    restart: unless-stopped
    env_file: ../.env
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 5s
      retries: 3
    stop_grace_period: 15s

  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: calendar_bot
      POSTGRES_USER: bot
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U bot -d calendar_bot"]
      interval: 10s
      timeout: 3s
      retries: 5

  nginx:
    image: nginx:alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/bot.conf:/etc/nginx/conf.d/default.conf
      - ./certbot/conf:/etc/letsencrypt
      - ./certbot/www:/var/www/certbot
    depends_on:
      - app

volumes:
  pgdata:
```

### Dockerfile

```dockerfile
FROM python:3.12-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

### Обновление (zero-downtime нет, но с минимальным простоем)

```bash
cd telegram-calendar-bot
git pull origin main
docker compose -f deploy/docker-compose.yml build app
docker compose -f deploy/docker-compose.yml up -d app
docker compose -f deploy/docker-compose.yml exec app alembic upgrade head
```

---

## CI/CD

### GitHub Actions: CI (на каждый PR)

```yaml
# .github/workflows/ci.yml
name: CI

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: ruff check src/ tests/
      - run: ruff format --check src/ tests/
      - run: mypy src/

  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_DB: calendar_bot_test
          POSTGRES_USER: bot
          POSTGRES_PASSWORD: testpass
        ports:
          - 5432:5432
        options: >-
          --health-cmd="pg_isready -U bot"
          --health-interval=10s
          --health-timeout=5s
          --health-retries=5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: pytest --cov=src --cov-report=xml
        env:
          TEST_DATABASE_URL: postgresql+asyncpg://bot:testpass@localhost:5432/calendar_bot_test
          ENCRYPTION_KEY: test-fernet-key-for-ci-only
```

### GitHub Actions: Deploy (при мерже в main)

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    if: github.event_name == 'push'
    needs: [lint, test]  # Зависит от CI
    steps:
      - name: Deploy to VPS
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.VPS_HOST }}
          username: deploy
          key: ${{ secrets.VPS_SSH_KEY }}
          script: |
            cd ~/telegram-calendar-bot
            git pull origin main
            docker compose -f deploy/docker-compose.yml build app
            docker compose -f deploy/docker-compose.yml up -d app
            docker compose -f deploy/docker-compose.yml exec -T app alembic upgrade head
```

### Настройка GitHub Secrets

В Settings → Secrets and variables → Actions добавьте:

| Secret          | Описание                            |
|----------------|-------------------------------------|
| `VPS_HOST`     | IP-адрес или домен вашего VPS        |
| `VPS_SSH_KEY`  | Приватный SSH-ключ пользователя deploy |

---

## Мониторинг и логирование

### Логи

Приложение пишет структурированные JSON-логи через structlog:

```json
{
  "event": "event_created",
  "user_id": 42,
  "event_title": "тренировка",
  "google_event_id": "abc123",
  "latency_ms": 340,
  "timestamp": "2026-04-02T12:00:00Z",
  "level": "info"
}
```

Просмотр логов:

```bash
# Все логи приложения:
docker compose -f deploy/docker-compose.yml logs -f app

# Фильтрация по уровню (через jq):
docker compose -f deploy/docker-compose.yml logs app | jq 'select(.level == "error")'
```

### Sentry

Для продакшена подключите Sentry (бесплатный тариф — 5к ошибок/мес):

1. Создайте проект на [sentry.io](https://sentry.io/)
2. Добавьте `SENTRY_DSN` в `.env`
3. SDK уже интегрирован в приложение и отлавливает необработанные исключения

### Healthcheck

`GET /health` возвращает:

```json
{
  "status": "ok",
  "database": "connected",
  "uptime_seconds": 86400
}
```

Используется для Docker healthcheck и внешнего мониторинга (UptimeRobot, бесплатный тариф).

---

## API Reference

| Endpoint                       | Метод | Описание                        | Аутентификация              |
|-------------------------------|-------|---------------------------------|-----------------------------|
| `/webhook/telegram`           | POST  | Приём обновлений от Telegram     | Telegram secret token       |
| `/auth/google/callback`       | GET   | OAuth callback от Google         | State parameter (CSRF)      |
| `/health`                     | GET   | Healthcheck                      | Нет                         |

> Бот не предоставляет публичный REST API. Всё взаимодействие — через Telegram.

---

## Troubleshooting

### Бот не отвечает на сообщения

```bash
# 1. Проверьте, установлен ли webhook:
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
# Убедитесь, что url совпадает с вашим доменом и нет pending_update_count > 100

# 2. Проверьте логи:
docker compose -f deploy/docker-compose.yml logs --tail=50 app

# 3. Проверьте доступность endpoint:
curl -I https://your-domain.com/health
```

### Ошибка "invalid_grant" при создании события

Refresh token стал невалидным (пользователь отозвал доступ или токен протух). Бот должен отправить пользователю сообщение с предложением повторного `/connect`. Проверьте логи на наличие `token_refresh_failed`.

### Миграции не применяются

```bash
# Проверьте текущую версию:
docker compose -f deploy/docker-compose.yml exec app alembic current

# Посмотрите историю:
docker compose -f deploy/docker-compose.yml exec app alembic history

# Принудительно поставить версию (осторожно!):
docker compose -f deploy/docker-compose.yml exec app alembic stamp head
```

### PostgreSQL: "too many connections"

По умолчанию PostgreSQL держит 100 соединений. Если запускаете несколько реплик приложения, добавьте PgBouncer или уменьшите pool_size в SQLAlchemy:

```python
# В src/db/session.py:
engine = create_async_engine(DATABASE_URL, pool_size=5, max_overflow=10)
```

---

## Roadmap

### v0.1 — MVP

- [ ] Базовая структура проекта и Docker-setup
- [ ] OAuth-авторизация с Google
- [ ] Парсинг текста через dateparser
- [ ] Создание событий с подтверждением
- [ ] Шифрование токенов
- [ ] Unit-тесты парсера
- [ ] Деплой на VPS

### v0.2 — Надёжность

- [ ] Retry-логика для Google API
- [ ] Фоновая задача: повтор зависших событий
- [ ] Проактивное обновление токенов
- [ ] Обработка отозванного OAuth-доступа
- [ ] Rate limiting на уровне пользователя
- [ ] Sentry-интеграция
- [ ] Интеграционные тесты

### v0.3 — UX

- [ ] Команда `/list` — предстоящие события
- [ ] Удаление событий через inline-кнопки
- [ ] Предупреждение о конфликтах (наложение событий)
- [ ] Поддержка длительности (`тренировка 1.5 часа`)
- [ ] Редактирование созданного события

### v1.0 — Продукт

- [ ] Прохождение Google OAuth верификации
- [ ] LLM-парсер (Claude API) для сложных случаев
- [ ] Поддержка повторяющихся событий (`каждый вторник`)
- [ ] Напоминания перед событием
- [ ] Мультикалендарность (выбор целевого календаря)

### Будущее

- Redis (кэш токенов + rate limiter для Google API)
- Очередь задач (arq или Celery) для разделения webhook и обработки
- Web-интерфейс
- Голосовые сообщения (Whisper API → текст → событие)
- Поддержка других календарей (Outlook, Apple)

---

## Contributing

Проект на ранней стадии. Если хотите внести вклад:

1. Форкните репозиторий
2. Создайте feature-ветку: `git checkout -b feature/my-feature`
3. Установите pre-commit хуки: `pre-commit install`
4. Напишите тесты для новой функциональности
5. Убедитесь, что все проверки проходят: `pytest && ruff check src/`
6. Создайте Pull Request

### Git-конвенции

Формат коммитов — [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: добавлена команда /list
fix: исправлен парсинг "послезавтра"
docs: обновлён README
refactor: вынесен encryption в отдельный модуль
test: добавлены кейсы для парсера
chore: обновлены зависимости
```

### Ветки

- `main` — стабильная версия, деплоится автоматически
- `develop` — текущая разработка
- `feature/*` — новые функции
- `fix/*` — исправления

---

## Лицензия

MIT License. См. файл [LICENSE](LICENSE).