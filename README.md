# Финансовый трекер

Python + Flask + **PostgreSQL (Supabase)**. Chart.js, деплой на Railway.

## Переменные окружения

Скопируйте `.env.example` в `.env`:

```env
DATABASE_URL=postgresql://postgres:PASSWORD@db.PROJECT.supabase.co:5432/postgres
SECRET_KEY=your-random-secret
DEFAULT_CURRENCY=€
```

В Supabase: **Project Settings → Database → Connection string** (URI).  
Для Railway добавьте те же переменные в **Variables**.

## Локальный запуск

```bat
start.bat
```

```bash
chmod +x start.sh && ./start.sh
```

Откройте http://127.0.0.1:5000 — таблицы создаются при первом запуске (`init_db`).

## Railway

```bash
railway variables set DATABASE_URL="postgresql://..."
railway variables set SECRET_KEY="..."
railway up
```

`Procfile`: `web: gunicorn app:app`

## Страницы

| URL | Раздел |
|-----|--------|
| `/` | Дашборд |
| `/income` | Приходы |
| `/budget` | Бюджет |
| `/savings` | Накопления |
| `/history` | История |
| `/settings` | Валюта |
