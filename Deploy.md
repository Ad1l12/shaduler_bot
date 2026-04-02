# Пошаговое руководство: от нуля до работающего бота в проде

Для каждого шага указано: делаешь **ты вручную** или **отдаёшь Claude Code**.

---

## Фаза 1: Подготовка аккаунтов и сервисов

> Всё в этой фазе — только вручную. Это регистрации, оплаты и настройки в веб-интерфейсах, где Claude Code не поможет.

### Шаг 1.1 — GitHub аккаунт

**Кто:** ты вручную

Ты сказал, что аккаунт новый. Проверь, что сделано:

1. Зайди на github.com, залогинься
2. Settings → Developer settings → Personal access tokens → Tokens (classic)
3. Нажми «Generate new token (classic)»
4. Scopes: поставь галочку на `repo` (полный доступ к репозиториям)
5. Нажми «Generate token», **скопируй токен сейчас** — потом его не увидишь
6. Сохрани токен временно в безопасное место (менеджер паролей, заметки с паролем)

Этот токен понадобится для пуша с локальной машины и для настройки деплоя.

### Шаг 1.2 — Создание репозитория на GitHub

**Кто:** ты вручную

1. github.com → «+» → New repository
2. Repository name: `telegram-calendar-bot`
3. Visibility: **Private** (в нём будут конфиги, и ты не хочешь, чтобы кто-то видел структуру)
4. НЕ ставь галочки на README, .gitignore, license — у тебя всё уже есть локально
5. Нажми «Create repository»
6. GitHub покажет инструкцию для «push an existing repository from the command line» — она понадобится в шаге 1.3

### Шаг 1.3 — Первый пуш в GitHub

**Кто:** Claude Code

Передай Claude Code:

```
В корне проекта выполни:
git init
git add .
git commit -m "feat: initial project structure (etaps 1-12)"
git branch -M main
git remote add origin https://github.com/<твой-username>/telegram-calendar-bot.git
git push -u origin main
```

> Если попросит авторизацию — введи username и вместо пароля вставь Personal Access Token из шага 1.1.

### Шаг 1.4 — Telegram Bot через @BotFather

**Кто:** ты вручную (в Telegram)

1. Открой Telegram, найди @BotFather
2. Отправь `/newbot`
3. Введи имя бота (отображаемое): `Calendar Assistant`
4. Введи username бота (уникальный): `my_calendar_assist_bot` (или придумай свой, должен заканчиваться на `bot`)
5. BotFather выдаст **токен** вида `7123456789:AAH...` — **сохрани его**
6. Отправь BotFather:

```
/setcommands
```

7. Выбери своего бота и отправь список команд:

```
start - Начать работу с ботом
connect - Подключить Google Calendar
disconnect - Отключить Google Calendar
list - Показать предстоящие события
timezone - Установить часовой пояс
help - Справка
```

**Запиши:**
- `TELEGRAM_BOT_TOKEN` = токен от BotFather

### Шаг 1.5 — Google Cloud Project + OAuth

**Кто:** ты вручную (в браузере)

Это самый длинный шаг. Делай по порядку, не пропускай.

**1.5.1. Создание проекта:**

1. Перейди на https://console.cloud.google.com/
2. В верхней панели нажми на выпадающий список проектов → «New Project»
3. Название: `telegram-calendar-bot`
4. Organization: оставь пустым (или выбери свою, если есть)
5. Нажми «Create» и дождись создания
6. Убедись, что новый проект выбран в верхней панели

**1.5.2. Включение Calendar API:**

1. В левом меню: APIs & Services → Library
2. В поиске набери: `Google Calendar API`
3. Нажми на него → «Enable»

**1.5.3. Настройка OAuth consent screen:**

1. APIs & Services → OAuth consent screen
2. User type: **External** → Create
3. Заполни:
   - App name: `Calendar Assistant Bot`
   - User support email: твой email
   - Developer contact: твой email
4. Нажми «Save and Continue»
5. Scopes → Add or Remove Scopes → в фильтре найди `Google Calendar API` → поставь галочку на `https://www.googleapis.com/auth/calendar.events` → Update → Save and Continue
6. Test users → Add Users → добавь **свой Gmail** (тот, к чьему календарю будешь подключаться) → Save and Continue
7. Summary → Back to Dashboard

> **Важно:** Пока приложение в статусе «Testing», работать будет только для тестовых пользователей (макс. 100). Для выхода в прод нужна верификация — но это потом.

**1.5.4. Создание OAuth credentials:**

1. APIs & Services → Credentials
2. «+ Create Credentials» → OAuth client ID
3. Application type: **Web application**
4. Name: `Calendar Bot Web Client`
5. Authorized redirect URIs → Add URI: `https://твой-домен.com/auth/google/callback`
   - Домена пока нет — **впиши заглушку**, потом поменяешь (шаг 2.6)
   - Для локального тестирования можешь добавить: `http://localhost:8000/auth/google/callback`
6. Нажми «Create»
7. Появится попап с Client ID и Client Secret — **скопируй оба**

**Запиши:**
- `GOOGLE_CLIENT_ID` = что-то вроде `123456-abc.apps.googleusercontent.com`
- `GOOGLE_CLIENT_SECRET` = что-то вроде `GOCSPX-xxxxxx`

---

## Фаза 2: Аренда сервера и настройка

### Шаг 2.1 — Выбор и аренда VPS

**Кто:** ты вручную

Рекомендую Hetzner — дёшево, надёжно, дата-центры в Европе (Хельсинки, Фалькенштайн).

1. Зайди на https://www.hetzner.com/cloud/
2. Зарегистрируйся (нужна кредитная карта)
3. Создай новый проект
4. Создай сервер:
   - Location: Helsinki (или Falkenstein — что ближе)
   - Image: **Ubuntu 24.04**
   - Type: **CX22** (2 vCPU, 4 GB RAM, 40 GB SSD) — ~€4.5/мес, хватит с запасом
   - SSH Key: **добавь свой публичный ключ** (если нет — сгенерируй, см. ниже)
   - Имя: `calendar-bot`
5. Нажми «Create & Buy Now»

**Если у тебя нет SSH-ключа:**

На своей локальной машине в терминале:

```bash
ssh-keygen -t ed25519 -C "your-email@example.com"
# Нажми Enter на все вопросы (или задай passphrase)
cat ~/.ssh/id_ed25519.pub
# Скопируй вывод — это публичный ключ, его вставишь в Hetzner
```

**Запиши:**
- IP-адрес сервера (покажется после создания, например `88.198.xx.xx`)

### Шаг 2.2 — Покупка домена

**Кто:** ты вручную

Бот технически может работать по IP, но для SSL-сертификата (Let's Encrypt) и OAuth redirect URI нужен домен.

Варианты:
- **Namecheap** — дешёвые .com домены (~$9/год)
- **Cloudflare Registrar** — по себестоимости, без наценки
- **Porkbun** — дёшево, удобный интерфейс

1. Купи домен (например `calbot.example.com` или что угодно)
2. В DNS-настройках домена создай **A-запись**:
   - Name: `@` (или `bot`, если хочешь поддомен `bot.example.com`)
   - Type: `A`
   - Value: IP-адрес твоего VPS из шага 2.1
   - TTL: 300 (5 минут)
3. Подожди 5–15 минут, пока DNS пропагируется

**Проверка** (с локальной машины):

```bash
ping твой-домен.com
# Должен отвечать IP-адрес твоего VPS
```

### Шаг 2.3 — Обновление Google OAuth redirect URI

**Кто:** ты вручную

Теперь, когда домен есть:

1. Вернись в Google Cloud Console → APIs & Services → Credentials
2. Открой свой OAuth Client ID
3. В Authorized redirect URIs замени заглушку на: `https://твой-домен.com/auth/google/callback`
4. Сохрани

### Шаг 2.4 — Первое подключение к серверу

**Кто:** ты вручную (в терминале)

```bash
ssh root@88.198.xx.xx
```

Если всё правильно — ты внутри сервера.

### Шаг 2.5 — Настройка сервера

**Кто:** ты вручную (по SSH на сервере). Команды ниже — копируй и вставляй блоками.

**2.5.1. Обновление системы:**

```bash
apt update && apt upgrade -y
```

**2.5.2. Установка Docker:**

```bash
curl -fsSL https://get.docker.com | sh
```

Проверка:

```bash
docker --version
# Docker version 27.x.x
docker compose version
# Docker Compose version v2.x.x
```

**2.5.3. Создание пользователя deploy (не работаем от root):**

```bash
# Создаём пользователя
adduser deploy
# Придумай пароль, остальные поля можно оставить пустыми (Enter)

# Даём права на Docker
usermod -aG docker deploy

# Даём sudo (понадобится для certbot)
usermod -aG sudo deploy

# Копируем SSH-ключ, чтобы заходить как deploy
mkdir -p /home/deploy/.ssh
cp /root/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys
```

**2.5.4. Проверка — зайди как deploy:**

```bash
# Выйди из root-сессии:
exit

# Зайди как deploy:
ssh deploy@88.198.xx.xx

# Проверь Docker:
docker ps
# Должен показать пустой список (а не ошибку "permission denied")
```

**2.5.5. Базовый файрвол:**

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
# Подтверди: y
sudo ufw status
```

### Шаг 2.6 — Клонирование проекта на сервер

**Кто:** ты вручную (по SSH, под пользователем deploy)

```bash
cd ~
git clone https://github.com/<твой-username>/telegram-calendar-bot.git
cd telegram-calendar-bot
```

> Если репозиторий приватный, Git попросит авторизацию. Введи username и Personal Access Token из шага 1.1.

### Шаг 2.7 — Создание .env файла на сервере

**Кто:** ты вручную (по SSH)

```bash
cp .env.example .env
nano .env
```

Заполни **каждую строку**:

```ini
APP_ENV=production
APP_LOG_LEVEL=INFO
APP_BASE_URL=https://твой-домен.com

TELEGRAM_BOT_TOKEN=7123456789:AAH...     # Из шага 1.4
TELEGRAM_WEBHOOK_SECRET=<сгенерируй>      # См. ниже

GOOGLE_CLIENT_ID=123456-abc.apps...       # Из шага 1.5
GOOGLE_CLIENT_SECRET=GOCSPX-xxx           # Из шага 1.5
GOOGLE_REDIRECT_URI=https://твой-домен.com/auth/google/callback

DATABASE_URL=postgresql+asyncpg://bot:<придумай-пароль>@db:5432/calendar_bot
DB_PASSWORD=<тот-же-пароль>

ENCRYPTION_KEY=<сгенерируй>               # См. ниже

SENTRY_DSN=                               # Пока пусто, добавишь позже
```

**Генерация секретов** (выполни прямо на сервере):

```bash
# Webhook secret:
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Encryption key:
pip3 install cryptography --break-system-packages
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Скопируй результаты в .env. Сохрани файл: `Ctrl+O`, `Enter`, `Ctrl+X`.

**Проверь, что .env не попадёт в Git:**

```bash
cat .gitignore | grep .env
# Должно быть: .env
```

---

## Фаза 3: Запуск

### Шаг 3.1 — SSL-сертификат

**Кто:** ты вручную (по SSH)

```bash
cd ~/telegram-calendar-bot

# Сделай скрипт исполняемым:
chmod +x deploy/init-letsencrypt.sh

# Отредактируй скрипт — укажи свой домен и email:
nano deploy/init-letsencrypt.sh
# Найди переменные DOMAIN и EMAIL, замени на свои

# Запусти:
sudo ./deploy/init-letsencrypt.sh
```

Скрипт:
1. Создаст временный self-signed сертификат
2. Запустит Nginx
3. Получит настоящий сертификат от Let's Encrypt
4. Перезапустит Nginx

**Если ошибка** «Challenge failed» — DNS ещё не пропагировался. Подожди 10 минут и повтори.

### Шаг 3.2 — Запуск всего стека

**Кто:** ты вручную (по SSH)

```bash
cd ~/telegram-calendar-bot

# Собери и запусти:
docker compose -f deploy/docker-compose.yml up -d --build

# Проверь, что все контейнеры running:
docker compose -f deploy/docker-compose.yml ps
# Ожидаемо: app, db, nginx — все Status: Up

# Проверь логи (убедись, что нет ошибок):
docker compose -f deploy/docker-compose.yml logs app --tail=30
```

### Шаг 3.3 — Миграции

**Кто:** ты вручную (по SSH)

```bash
docker compose -f deploy/docker-compose.yml exec app alembic upgrade head
```

Ожидаемый вывод: `Running upgrade -> xxxx, initial migration`

### Шаг 3.4 — Проверка healthcheck

**Кто:** ты вручную (с любого устройства)

```bash
curl https://твой-домен.com/health
```

Ожидаемый ответ:

```json
{"status": "ok", "uptime_seconds": 5.2, "db": "ok"}
```

Если `"db": "error"` — проблема с подключением к PostgreSQL. Проверь `DATABASE_URL` в .env (хост должен быть `db`, не `localhost`).

### Шаг 3.5 — Установка Telegram Webhook

**Кто:** ты вручную (с любого устройства или с сервера)

```bash
curl -X POST "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://твой-домен.com/webhook/telegram",
    "secret_token": "<TELEGRAM_WEBHOOK_SECRET из .env>",
    "max_connections": 40,
    "allowed_updates": ["message", "callback_query"]
  }'
```

Ожидаемый ответ:

```json
{"ok": true, "result": true, "description": "Webhook was set"}
```

**Проверка:**

```bash
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

Убедись, что `url` правильный, `last_error_date` отсутствует или пустой.

### Шаг 3.6 — Первый тест бота

**Кто:** ты вручную (в Telegram)

1. Открой своего бота в Telegram
2. Отправь `/start` — должен ответить приветствием
3. Отправь `/connect` — должен дать ссылку на Google OAuth
4. Перейди по ссылке, авторизуйся через Google
5. После успешного callback отправь боту: `завтра в 18 тренировка`
6. Бот должен показать превью и кнопку «Создать»
7. Нажми «Создать»
8. Проверь Google Calendar — событие должно быть там

**Если что-то не работает** — смотри логи:

```bash
docker compose -f deploy/docker-compose.yml logs -f app
```

---

## Фаза 4: Настройка CI/CD (автоматический деплой)

### Шаг 4.1 — SSH-ключ для GitHub Actions

**Кто:** ты вручную (на сервере по SSH)

GitHub Actions будет подключаться к серверу для деплоя. Нужен отдельный SSH-ключ.

```bash
# На сервере, под пользователем deploy:
ssh-keygen -t ed25519 -f ~/.ssh/github_actions -C "github-actions-deploy" -N ""

# Добавь публичный ключ в authorized_keys:
cat ~/.ssh/github_actions.pub >> ~/.ssh/authorized_keys

# Выведи приватный ключ (понадобится для GitHub):
cat ~/.ssh/github_actions
# Скопируй ВЕСЬ вывод, включая -----BEGIN и -----END
```

### Шаг 4.2 — GitHub Secrets

**Кто:** ты вручную (в браузере)

1. Зайди в свой репозиторий на GitHub
2. Settings → Secrets and variables → Actions
3. Нажми «New repository secret» и добавь:

| Name          | Value                                     |
|---------------|-------------------------------------------|
| `VPS_HOST`    | IP-адрес или домен сервера                 |
| `VPS_SSH_KEY` | Приватный ключ из шага 4.1 (весь текст)    |

### Шаг 4.3 — Проверка CI

**Кто:** ты + Claude Code

1. Внеси любое изменение в код (например, добавь комментарий в `README.md`)
2. Попроси Claude Code:

```
Сделай git add, commit "chore: test CI pipeline" и push в main.
```

3. Зайди на GitHub → вкладка Actions
4. Должен запуститься workflow CI: lint → test
5. Если CI зелёный — автоматически запустится Deploy
6. Проверь на сервере:

```bash
docker compose -f deploy/docker-compose.yml logs --tail=5 app
# Должен быть свежий лог (с актуальным временем)
```

---

## Фаза 5: Мониторинг (опционально, но рекомендую)

### Шаг 5.1 — Sentry

**Кто:** ты вручную

1. Зайди на https://sentry.io/ → Sign up (бесплатный план: 5000 ошибок/мес)
2. Создай проект: Platform → Python → FastAPI
3. Скопируй DSN (будет вида `https://abc123@o456.ingest.sentry.io/789`)
4. На сервере добавь в .env:

```bash
ssh deploy@88.198.xx.xx
cd ~/telegram-calendar-bot
nano .env
# Добавь: SENTRY_DSN=https://abc123@o456.ingest.sentry.io/789
```

5. Перезапусти приложение:

```bash
docker compose -f deploy/docker-compose.yml restart app
```

### Шаг 5.2 — Uptime-мониторинг

**Кто:** ты вручную

1. Зайди на https://uptimerobot.com/ → Sign up (бесплатный план: 50 мониторов)
2. Add New Monitor:
   - Monitor Type: HTTPS
   - Friendly Name: `Calendar Bot Health`
   - URL: `https://твой-домен.com/health`
   - Monitoring Interval: 5 minutes
3. Alert Contacts: добавь свой email или Telegram (UptimeRobot умеет слать в Telegram)

Теперь если бот упадёт — получишь уведомление в течение 5 минут.

---

## Фаза 6: Повседневные операции

### Как обновить код

Два варианта:

**Автоматически (через CI/CD):**

Просто пушь в `main` — GitHub Actions сам задеплоит.

**Вручную (если CI/CD сломан):**

```bash
ssh deploy@88.198.xx.xx
cd ~/telegram-calendar-bot
git pull origin main
docker compose -f deploy/docker-compose.yml build app
docker compose -f deploy/docker-compose.yml up -d app
docker compose -f deploy/docker-compose.yml exec app alembic upgrade head
```

### Как смотреть логи

```bash
# Все логи в реальном времени:
docker compose -f deploy/docker-compose.yml logs -f app

# Только ошибки (через jq):
docker compose -f deploy/docker-compose.yml logs app 2>&1 | grep '"level":"error"'

# Логи за последний час:
docker compose -f deploy/docker-compose.yml logs --since 1h app
```

### Как перезапустить

```bash
# Только приложение (БД не трогаем):
docker compose -f deploy/docker-compose.yml restart app

# Всё целиком:
docker compose -f deploy/docker-compose.yml down
docker compose -f deploy/docker-compose.yml up -d
```

### Как сделать бэкап БД

```bash
# Дамп:
docker compose -f deploy/docker-compose.yml exec db \
  pg_dump -U bot calendar_bot > backup_$(date +%Y%m%d).sql

# Восстановление:
cat backup_20260402.sql | docker compose -f deploy/docker-compose.yml exec -T db \
  psql -U bot calendar_bot
```

### Как обновить SSL-сертификат

Certbot в docker-compose настроен на авторенью каждые 12 часов. Если нужно вручную:

```bash
docker compose -f deploy/docker-compose.yml run --rm certbot renew
docker compose -f deploy/docker-compose.yml exec nginx nginx -s reload
```

---

## Чеклист: что записать

По мере прохождения руководства у тебя накопятся секреты. Вот полный список — убедись, что все записаны:

| Секрет                         | Где получил      | Где используется           |
|-------------------------------|------------------|-----------------------------|
| GitHub Personal Access Token   | Шаг 1.1          | git push, клонирование      |
| Telegram Bot Token             | Шаг 1.4          | .env на сервере              |
| Google Client ID               | Шаг 1.5          | .env на сервере              |
| Google Client Secret           | Шаг 1.5          | .env на сервере              |
| Webhook Secret                 | Шаг 2.7 (генер.) | .env на сервере              |
| Encryption Key (Fernet)        | Шаг 2.7 (генер.) | .env на сервере              |
| DB Password                    | Шаг 2.7 (придум.)| .env на сервере              |
| IP-адрес VPS                   | Шаг 2.1          | DNS, SSH, GitHub Secrets     |
| SSH-ключ (deploy)              | Шаг 4.1          | GitHub Secrets               |
| Sentry DSN                     | Шаг 5.1          | .env на сервере              |

**Все эти значения хранятся только в двух местах:**
1. `.env` на сервере (не в Git!)
2. GitHub Secrets (для CI/CD)

Нигде больше. Не отправляй их в чаты, не коммить в репозиторий.