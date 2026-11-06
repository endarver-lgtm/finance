DASHBOARD_PERIODS = {
    "day": "День",
    "week": "Неделя",
    "month": "Месяц",
    "year": "Год",
}

BUDGET_PERIODS = {
    "week": "Неделя",
    "month": "Месяц",
}

CURRENCIES = {
    "BYN": "BYN — бел. рубль",
    "USD": "USD — доллар",
    "EUR": "EUR — евро",
}

BASE_CURRENCY = "BYN"

INCOME_TYPE_LABELS = {
    "regular": "Регулярный",
    "one_time": "Разовый",
}

INCOME_FREQ_LABELS = {
    "weekly": "Еженедельно",
    "monthly": "Ежемесячно",
    "one_time": "Разово",
}

SAVINGS_TYPE_GROUPS = {
    "want": "Хотелки",
    "reserve": "Резерв",
    "big": "Крупные цели",
}

HISTORY_KIND_LABELS = {
    "income": "Приход",
    "expense": "Расход",
    "savings": "Накопление",
    "savings_withdraw": "Снятие из копилки",
    "debt": "Долг",
}

ONE_TIME_INCOME_LABEL = "Разовый доход"

# --- Единые аналитические пороги (Этап 0.5 / E1 / C) ---
ENVELOPE_PCT_THRESHOLDS = {
    "ok": 80.0,       # < 80% — ok (зеленый)
    "warning": 100.0, # 80..<100% — warning (желтый), >=100% — danger (красный)
}

TEMPO_RATIO_THRESHOLDS = {
    "ok": 1.0,        # ratio <= 1.0 — в графике
    "warning": 1.25,   # 1.0..1.25 — опережаете график, >1.25 — перерасход
}

SAVINGS_RATE_THRESHOLDS = {
    "ok": 20.0,       # >= 20% — Отлично
    "warning": 10.0,  # 10..20% — Норма, < 10% — Низкая
}

RUNWAY_THRESHOLDS = {
    "stellar": 6.0,   # >= 6 мес — Капитал
    "ok": 3.0,        # 3..6 мес — Надёжно
    "warning": 1.0,   # 1..3 мес — Минимум, < 1 мес — Критично
}

ADHERENCE_THRESHOLDS = {
    "ok": 80.0,       # >= 80% пар закрытых периодов в лимите
}

ACCURACY_THRESHOLDS = {
    "ok": 2.0,        # Неучтенного <= 2% — ok
    "warning": 5.0,   # 2..5% — warning, > 5% — danger
}
