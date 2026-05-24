# 💰 Finance Tracker

> Личный финансовый трекер: приходы, бюджет-конверты, накопления и история — в белорусских рублях с оценкой в долларах.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.0-000000?style=flat-square&logo=flask&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-локально-003B57?style=flat-square&logo=sqlite&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)

---

## ✨ Возможности

| Раздел | Что умеет |
|--------|-----------|
| **Дашборд** | KPI (план / факт), графики расходов и приходов, конверты недели, ожидаемые поступления |
| **Приходы** | Источники дохода, разовые поступления, статус «получено / ожидается» |
| **Бюджет** | Конверты с лимитом на неделю или месяц, списания блоком, прогресс-бар |
| **Накопления** | Цели: хотелки, резерв, крупные покупки |
| **История** | Все операции в одной таблице с фильтрами |
| **Настройки** | Курс BYN → USD для примерной оценки в $ |

**Валюта:** суммы в **BYN**, рядом везде **≈ $** (курс настраивается).

**Периоды:** день · неделя · месяц · год (на дашборде и приходах).

---

## 🖼 Скриншоты

<!-- Добавьте скриншоты в docs/screenshots/ и раскомментируйте:

![Дашборд](docs/screenshots/dashboard.png)
![Бюджет](docs/screenshots/budget.png)

-->

> Скриншоты можно положить в `docs/screenshots/` и вставить ссылки выше.

---

## 🛠 Стек

| Слой | Технологии |
|------|------------|
| Backend | Python, Flask, SQLite |
| Frontend | Jinja2, CSS, Chart.js |
| Шрифт | [Inter](https://fonts.google.com/specimen/Inter) |
| Продакшен | Gunicorn (`Procfile`) |

**Дизайн:** светлый UI · карточки `#FFFFFF` · акцент `#4ADE80` · скругления 16px · адаптив (нижнее меню на телефоне).

---

## 🚀 Быстрый старт

### Windows

```bat
git clone https://github.com/YOUR_USERNAME/finance.git
cd finance
start.bat
```

Откройте в браузере: **http://127.0.0.1:5000**

### macOS / Linux

```bash
git clone https://github.com/YOUR_USERNAME/finance.git
cd finance
chmod +x start.sh
./start.sh
```

`start.bat` / `start.sh` сами создают `.venv`, ставят зависимости и поднимают сервер.

### Вручную

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Unix:     source .venv/bin/activate
pip install -r requirements.txt
set FLASK_DEBUG=1          # Windows
export FLASK_DEBUG=1     # macOS / Linux
python app.py
```

---

## ⚙️ Настройки

Скопируйте пример окружения:

```bash
cp .env.example .env
```

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `DATABASE_PATH` | Путь к файлу SQLite | `./finance.db` |
| `SECRET_KEY` | Секрет Flask (сессии) | dev-ключ |
| `USD_RATE` | BYN за 1 USD (для ≈ $) | `3.27` |
| `DEFAULT_CURRENCY` | Метка валюты | `BYN` |

Курс можно менять в интерфейсе: **Настройки → Курс для оценки в долларах**.

---

## 📋 Команды

| Команда | Действие |
|---------|----------|
| `start.bat` / `./start.sh` | Запуск dev-сервера |
| `reset.bat` | Полная очистка БД |
| `python manage.py reset` | То же из терминала |

После `reset` база пустая, настройки: **BYN**, курс **3.27**.

---

## 📁 Структура проекта

```
finance/
├── app.py                 # Точка входа Flask
├── manage.py              # CLI (reset)
├── config.py              # Конфиг и .env
├── db/
│   ├── schema.py          # Таблицы SQLite
│   ├── connection.py      # get_db()
│   └── settings.py        # Настройки приложения
├── routes/                # Страницы (blueprints)
├── services/
│   ├── analytics.py       # KPI, графики, история
│   ├── repository.py      # CRUD и запросы
│   ├── planning.py        # План vs период
│   ├── currency.py        # BYN → USD
│   └── constants.py       # Подписи UI
├── templates/             # Jinja2
├── static/
│   ├── css/style.css
│   └── js/                # Chart.js, модалки
├── start.bat / start.sh
├── reset.bat
└── Procfile               # gunicorn для деплоя
```

---

## 🗄 База данных

SQLite, один файл `finance.db`:

- `income_sources` / `income_entries` — приходы  
- `budget_categories` / `budget_entries` — конверты  
- `savings_goals` / `savings_entries` — накопления  
- `settings` — валюта и курс USD  

Таблицы создаются автоматически при первом запуске.

---

## 🌐 Деплой

```bash
# Пример: Railway / Render
gunicorn app:app --bind 0.0.0.0:$PORT
```

> На бесплатном хостинге файл SQLite может **обнуляться** при пересборке. Для постоянных данных используйте volume или внешнюю БД.

---

## 🗺 Маршруты

| URL | Страница |
|-----|----------|
| `/` | Дашборд |
| `/income` | Приходы |
| `/budget` | Бюджет |
| `/savings` | Накопления |
| `/history` | История |
| `/settings` | Настройки |

---

## 🤝 Разработка

```bash
pip install -r requirements.txt
python manage.py reset   # чистая БД
python app.py
```

Идеи для PR: тёмная тема, экспорт CSV, API, мобильное PWA.

---

## 📄 Лицензия

MIT — используйте свободно, на свой страх и риск.

---

<p align="center">
  Сделано для учёта личных финансов в <strong>BYN</strong> 🇧🇾
</p>
