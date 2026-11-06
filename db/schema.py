# Idempotent SQLite DDL (CREATE TABLE IF NOT EXISTS). Safe to run on every app boot.

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS income_sources (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        type TEXT NOT NULL CHECK (type IN ('regular', 'one_time')),
        planned_amount REAL NOT NULL DEFAULT 0,
        currency TEXT NOT NULL DEFAULT 'BYN',
        frequency TEXT NOT NULL CHECK (frequency IN ('weekly', 'monthly', 'one_time')),
        active INTEGER NOT NULL DEFAULT 1,
        expected_date TEXT,
        pay_days TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS income_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id INTEGER,
        amount REAL NOT NULL,
        currency TEXT NOT NULL DEFAULT 'BYN',
        date TEXT NOT NULL,
        comment TEXT,
        rate_usd REAL,
        rate_eur REAL,
        amount_byn REAL,
        fx_source TEXT DEFAULT 'entry',
        created_at TEXT NOT NULL,
        FOREIGN KEY (source_id) REFERENCES income_sources(id) ON DELETE SET NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS budget_categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        planned_amount REAL NOT NULL DEFAULT 0,
        currency TEXT NOT NULL DEFAULT 'BYN',
        period TEXT NOT NULL CHECK (period IN ('week', 'month')),
        is_system INTEGER NOT NULL DEFAULT 0,
        track_only INTEGER NOT NULL DEFAULT 0,
        is_fixed INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS budget_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        currency TEXT NOT NULL DEFAULT 'BYN',
        date TEXT NOT NULL,
        comment TEXT,
        from_goal_id INTEGER,
        rate_usd REAL,
        rate_eur REAL,
        amount_byn REAL,
        fx_source TEXT DEFAULT 'entry',
        created_at TEXT NOT NULL,
        FOREIGN KEY (category_id) REFERENCES budget_categories(id) ON DELETE CASCADE,
        FOREIGN KEY (from_goal_id) REFERENCES savings_goals(id) ON DELETE SET NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS savings_goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        type TEXT NOT NULL CHECK (type IN ('want', 'reserve', 'big')),
        target_amount REAL NOT NULL DEFAULT 0,
        currency TEXT NOT NULL DEFAULT 'BYN',
        deadline TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS savings_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        goal_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        currency TEXT NOT NULL DEFAULT 'BYN',
        date TEXT NOT NULL,
        comment TEXT,
        kind TEXT NOT NULL DEFAULT 'deposit',
        budget_entry_id INTEGER,
        rate_usd REAL,
        rate_eur REAL,
        amount_byn REAL,
        fx_source TEXT DEFAULT 'entry',
        created_at TEXT NOT NULL,
        FOREIGN KEY (goal_id) REFERENCES savings_goals(id) ON DELETE CASCADE,
        FOREIGN KEY (budget_entry_id) REFERENCES budget_entries(id) ON DELETE SET NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS debts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        person TEXT NOT NULL,
        kind TEXT NOT NULL,
        amount REAL NOT NULL,
        currency TEXT NOT NULL DEFAULT 'BYN',
        date TEXT NOT NULL,
        comment TEXT,
        budget_entry_id INTEGER,
        rate_usd REAL,
        rate_eur REAL,
        amount_byn REAL,
        fx_source TEXT DEFAULT 'entry',
        created_at TEXT NOT NULL,
        FOREIGN KEY (budget_entry_id) REFERENCES budget_entries(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_debts_person_date ON debts(person, date)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_debts_budget_entry ON debts(budget_entry_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS balance_checks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        real_byn REAL NOT NULL,
        expected_byn REAL,
        diff_byn REAL,
        real_breakdown TEXT,
        savings_in_check INTEGER NOT NULL DEFAULT 1,
        adjust_expense_id INTEGER,
        adjust_income_id INTEGER,
        rate_usd REAL,
        rate_eur REAL,
        fx_effect_byn REAL DEFAULT 0,
        comment TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (adjust_expense_id) REFERENCES budget_entries(id) ON DELETE SET NULL,
        FOREIGN KEY (adjust_income_id) REFERENCES income_entries(id) ON DELETE SET NULL
    )
    """,
)

TABLES_DROP_ORDER = (
    "balance_checks",
    "debts",
    "savings_entries",
    "budget_entries",
    "income_entries",
    "savings_goals",
    "budget_categories",
    "income_sources",
    "settings",
)

DEFAULT_SETTINGS = (
    ("currency", "BYN"),
    ("usd_rate", "3.27"),
    ("eur_rate", "3.55"),
    ("savings_in_check", "1"),
    ("default_debt_person", "Кент"),
    ("ai_api_key", ""),
    ("ai_model", "qwen/qwen3.8-27b"),
    ("ai_provider", "groq"),
)

CURRENCY_COLUMNS = (
    ("income_sources", "currency"),
    ("income_entries", "currency"),
    ("budget_categories", "currency"),
    ("budget_entries", "currency"),
    ("savings_goals", "currency"),
    ("savings_entries", "currency"),
    ("debts", "currency"),
)
