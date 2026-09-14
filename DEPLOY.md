# Деплой: Render (приложение) + Supabase (БД)

Полная пошаговая инструкция: что нажать в каждом сервисе.

---

## Что получится

| Часть | Сервис | Зачем |
|-------|--------|--------|
| Веб-приложение (Flask + Gunicorn) | [Render](https://render.com) | Хостинг сайта, HTTPS, автодеплой из GitHub |
| База данных Postgres | [Supabase](https://supabase.com) | Постоянное хранение данных (не стирается при редеплое) |

SQLite больше не используется. Локальный файл `finance.db` в облако **не** попадёт.

---

## Чеклист (кратко)

1. Закоммитить и запушить код с Postgres-миграцией на GitHub.
2. Создать проект в Supabase → скопировать connection string.
3. Создать Web Service на Render из репозитория.
4. В Render Environment задать `DATABASE_URL` и `SECRET_KEY`.
5. Дождаться Deploy Live → открыть URL → проверить запись в Table Editor.

---

## Часть 0. Код на GitHub (обязательно сначала)

Render деплоит **только то, что лежит в GitHub**. Если миграция на Postgres ещё только локально — сначала:

```bat
git add -A
git status
git commit -m "Migrate to Postgres for Render + Supabase deploy"
git push origin main
```

Проверьте на https://github.com/endarver-lgtm/finance что в репо есть:

- `requirements.txt` с `psycopg2-binary` и `gunicorn`
- `Procfile` / `render.yaml`
- папка `db/` с Postgres-кодом
- `DEPLOY.md`, `.env.example`
- **нет** файла `.env` (пароли не коммитить)

`.env` уже в `.gitignore`.

---

## Часть 1. Supabase (база данных)

### 1.1. Аккаунт и проект

1. Откройте https://supabase.com → **Start your project** (войдите через GitHub).
2. **New project**:
   - **Name:** например `finance`
   - **Database Password:** придумайте сложный пароль и **сохраните его** (потом не покажут целиком).
   - **Region:** ближайший к вам / к Render (например Frankfurt / `eu-central-1`).
3. Дождитесь статуса **Project is ready**.

### 1.2. Строка подключения `DATABASE_URL`

1. В шапке проекта нажмите **Connect** (или **Project Settings** → **Database** → Connection string).
2. Выберите **Connection string** → тип **URI**.
3. Режим подключения для Render (важно):

| Режим | Порт | Когда брать |
|-------|------|-------------|
| **Session** pooler | **5432** на `*.pooler.supabase.com` | **Рекомендуется** для Flask + Gunicorn (долгоживущие воркеры) |
| **Transaction** pooler | **6543** на `*.pooler.supabase.com` | Тоже ок; меньше соединений |
| **Direct** | **5432** на `db.*.supabase.co` | Часто только IPv6 — на бесплатном Render может **не** подключиться |

Берите **Session** или **Transaction** pooler (оба дают IPv4). Не Direct, пока не уверены в IPv4.

4. Скопируйте URI. Вид примерно такой:

```text
postgresql://postgres.abcdefghijklmnop:YOUR_PASSWORD@aws-0-eu-central-1.pooler.supabase.com:5432/postgres
```

5. Замените `[YOUR-PASSWORD]` / плейсхолдер на реальный пароль БД.
6. Если в пароле есть спецсимволы (`@`, `#`, `%`, `/` и т.д.) — URL-encode их (например `@` → `%40`).

Приложение само добавит `sslmode=require`, если его нет в строке.

### 1.3. Таблицы (опционально)

При первом запуске приложения на Render таблицы создадутся сами (`CREATE IF NOT EXISTS`).

Либо вручную: **SQL Editor** → **New query** → вставьте содержимое [`supabase/schema.sql`](supabase/schema.sql) → **Run**.

### 1.4. Что не нужно в Supabase для этого проекта

- Auth / Login
- Storage
- Edge Functions
- Realtime

Достаточно только Postgres.

---

## Часть 2. Render (веб-сервис)

### 2.1. Новый Web Service

1. Откройте https://dashboard.render.com → войдите через GitHub.
2. **New +** → **Web Service**.
3. Подключите репозиторий `endarver-lgtm/finance` (Authorize GitHub, если просит).
4. Ветка: `main`.
5. Настройки:

| Поле | Значение |
|------|----------|
| **Name** | `finance-tracker` (или любое) |
| **Region** | ближе к региону Supabase (например Frankfurt) |
| **Language / Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120` |
| **Instance type** | Free (или выше) |

**Альтернатива:** **New +** → **Blueprint** → укажите репозиторий с `render.yaml` — часть полей заполнится сама. `DATABASE_URL` всё равно нужно вписать вручную в Environment.

### 2.2. Environment Variables

Сервис → **Environment** → **Add Environment Variable**:

| Key | Value |
|-----|--------|
| `DATABASE_URL` | строка из Supabase (часть 1.2), целиком, без кавычек |
| `SECRET_KEY` | длинная случайная строка (в Render можно **Generate**) |
| `DEFAULT_CURRENCY` | `BYN` (необязательно) |

**Не** задавайте `DATABASE_PATH` — это старый SQLite.

После сохранения переменных сделайте **Manual Deploy** → **Deploy latest commit**, если деплой уже шёл без `DATABASE_URL`.

### 2.3. Деплой и проверка логов

1. Дождитесь статуса **Live**.
2. Вкладка **Logs**:
   - хорошо: `Booting worker`, нет traceback;
   - плохо: `DATABASE_URL is not set` → переменная не задана;
   - плохо: `password authentication failed` → пароль / URL-encode;
   - плохо: `could not connect` / timeout → смените на Session/Transaction pooler, не Direct.
3. Откройте URL вида `https://finance-tracker-xxxx.onrender.com`.

На бесплатном плане первый запрос после простоя (~15 мин) может идти 30–60 секунд (cold start) — это нормально.

---

## Часть 3. Локальный запуск (та же Supabase БД)

1. Скопируйте пример окружения:

```bat
copy .env.example .env
```

2. В `.env` вставьте свой `DATABASE_URL` и `SECRET_KEY`.
3. Запуск:

```bat
start.bat
```

или:

```bash
pip install -r requirements.txt
python app.py
```

Очистить все данные в Postgres:

```bash
python manage.py reset
```

Проверка записи/чтения (осторожно: делает `reset`):

```bash
python scripts/verify_db.py
```

---

## Часть 4. Проверка, что облако связано

1. Откройте сайт на Render.
2. Добавьте тестовый приход / конверт.
3. В Supabase: **Table Editor** → таблицы `income_entries`, `budget_categories` и т.д. — должны появиться строки.

Если сайт открывается, а таблиц нет — смотрите Logs на Render: `init_db` мог упасть при старте.

---

## Частые ошибки

| Симптом | Что проверить |
|---------|----------------|
| На Render старый UI / SQLite-ошибки | Код с Postgres не запушен в GitHub |
| `DATABASE_URL is not set` | Переменная не добавлена в Render Environment / нет `.env` локально |
| `password authentication failed` | Неверный пароль в URI; спецсимволы не закодированы |
| `could not connect` / timeout / Network unreachable | Используется Direct (IPv6) — переключитесь на Session/Transaction pooler |
| `SSL connection required` | Добавьте `?sslmode=require` в конец URI |
| Сайт открывается, данные пропадают после редеплоя | Нет `DATABASE_URL` или всё ещё старый код без Postgres |
| `Too many connections` | Transaction pooler `:6543`, меньше gunicorn workers (`--workers 1`) |
| 502 / Application Error | Смотрите Logs; чаще всего БД или падение при `init_db()` |

---

## Безопасность (важно)

Сейчас в приложении **нет логина**. Любой, кто знает URL на Render, может читать и писать финансы.

Варианты:

1. Держать URL в секрете (слабо).
2. Render → Settings → **Password Protection** (на платных планах) или Cloudflare Access / Basic Auth перед сервисом.
3. Позже добавить авторизацию в само приложение.

---

## Миграция старых данных из `finance.db` (SQLite)

Если локально уже есть `finance.db` и нужно перенести записи в Supabase — напишите, можно сделать отдельный одноразовый скрипт экспорта. По умолчанию облако стартует с пустой БД и дефолтными курсами BYN/USD/EUR.
