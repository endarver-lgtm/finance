# Finance Tracker

Личный финансовый трекер: приходы, бюджет-конверты, накопления и история — в белорусских рублях с оценкой в долларах.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.0-000000?style=flat-square&logo=flask&logoColor=white)
![Postgres](https://img.shields.io/badge/Postgres-Supabase-3ECF8E?style=flat-square&logo=supabase&logoColor=white)
![Render](https://img.shields.io/badge/Deploy-Render-46E3B7?style=flat-square&logo=render&logoColor=white)

---

## Возможности

| Раздел | Что умеет |
|--------|-----------|
| **Дашборд** | KPI (план / факт), графики расходов и приходов, конверты недели, ожидаемые поступления |
| **Приходы** | Источники дохода, разовые поступления, статус «получено / ожидается» |
| **Бюджет** | Конверты с лимитом на неделю или месяц, списания блоком, прогресс-бар |
| **Накопления** | Цели: хотелки, резерв, крупные покупки |
| **История** | Все операции в одной таблице с фильтрами |
| **Настройки** | Курс BYN → USD для примерной оценки в $ |

---

## Стек

| Слой | Технологии |
|------|------------|
| Backend | Python, Flask, Gunicorn |
| БД | PostgreSQL (Supabase) |
| Frontend | Jinja2, CSS, Chart.js |
| Хостинг | Render |

Полная инструкция по деплою: **[DEPLOY.md](DEPLOY.md)**.

---

## Быстрый старт (локально)

1. Создайте проект в Supabase и скопируйте connection string (см. DEPLOY.md).
2. Настройте окружение:

```bat
copy .env.example .env
```

Вставьте `DATABASE_URL` и `SECRET_KEY` в `.env`.

3. Запуск:

```bat
start.bat
```

macOS / Linux:

```bash
chmod +x start.sh
./start.sh
```

Откройте http://127.0.0.1:5000

---

## Переменные окружения

| Переменная | Описание |
|------------|----------|
| `DATABASE_URL` | URI Postgres из Supabase (**обязательно**) |
| `SECRET_KEY` | Секрет Flask (сессии) |
| `DEFAULT_CURRENCY` | Метка валюты (по умолчанию `BYN`) |
| `USD_RATE` | Начальный курс для seed (дальше — в UI «Настройки») |

---

## Команды

| Команда | Действие |
|---------|----------|
| `start.bat` / `./start.sh` | Dev-сервер |
| `python manage.py reset` | Очистить все таблицы в Postgres и создать заново |

---

## Структура

```
finance/
├── app.py
├── config.py
├── db/                 # Postgres: схема, подключение, настройки
├── routes/
├── services/
├── templates/
├── static/
├── supabase/schema.sql # DDL для SQL Editor (опционально)
├── render.yaml
├── Procfile
└── DEPLOY.md           # Render + Supabase пошагово
```

---

## Деплой на Render

Кратко:

1. Supabase → проект → скопировать `DATABASE_URL`.
2. Render → Web Service из GitHub → Build/Start как в `Procfile` / `render.yaml`.
3. Environment: `DATABASE_URL`, `SECRET_KEY`.

Подробно со скриншотами шагов: **[DEPLOY.md](DEPLOY.md)**.

---

## Маршруты

| URL | Страница |
|-----|----------|
| `/` | Дашборд |
| `/income` | Приходы |
| `/budget` | Бюджет |
| `/savings` | Накопления |
| `/history` | История |
| `/settings` | Настройки |

---

## Лицензия

MIT
