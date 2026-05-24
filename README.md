# Финансовый трекер

Python + Flask + SQLite. Дизайн: Inter, карточки, Chart.js. Деплой на Railway.

## Локальный запуск

```bash
cd finance
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
python app.py
```

Откройте http://127.0.0.1:5000

## Railway

```bash
railway login
railway init
railway up
```

Переменные окружения (опционально):

- `SECRET_KEY` — секрет Flask
- `DATABASE_PATH` — путь к SQLite (на Railway лучше том `/data/finance.db`)

## Страницы

- **/** — дашборд (KPI, графики, конверты, приходы)
- **/income** — источники и поступления
- **/budget** — конверты (неделя / месяц)
- **/savings** — цели накоплений
- **/history** — единая история с фильтрами
- **/settings** — валюта (по умолчанию €)
