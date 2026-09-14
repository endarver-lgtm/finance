# Idempotent Postgres DDL (CREATE IF NOT EXISTS). Safe to run on every app boot.

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS income_sources (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        type TEXT NOT NULL CHECK (type IN ('regular', 'one_time')),
        planned_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
        currency TEXT NOT NULL DEFAULT 'BYN',
        frequency TEXT NOT NULL CHECK (frequency IN ('weekly', 'monthly', 'one_time')),
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS income_entries (
        id SERIAL PRIMARY KEY,
        source_id INTEGER REFERENCES income_sources(id) ON DELETE SET NULL,
        amount DOUBLE PRECISION NOT NULL,
        currency TEXT NOT NULL DEFAULT 'BYN',
        date TEXT NOT NULL,
        comment TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS budget_categories (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        planned_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
        currency TEXT NOT NULL DEFAULT 'BYN',
        period TEXT NOT NULL CHECK (period IN ('week', 'month')),
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS budget_entries (
        id SERIAL PRIMARY KEY,
        category_id INTEGER NOT NULL REFERENCES budget_categories(id) ON DELETE CASCADE,
        amount DOUBLE PRECISION NOT NULL,
        currency TEXT NOT NULL DEFAULT 'BYN',
        date TEXT NOT NULL,
        comment TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS savings_goals (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        type TEXT NOT NULL CHECK (type IN ('want', 'reserve', 'big')),
        target_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
        currency TEXT NOT NULL DEFAULT 'BYN',
        deadline TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS savings_entries (
        id SERIAL PRIMARY KEY,
        goal_id INTEGER NOT NULL REFERENCES savings_goals(id) ON DELETE CASCADE,
        amount DOUBLE PRECISION NOT NULL,
        currency TEXT NOT NULL DEFAULT 'BYN',
        date TEXT NOT NULL,
        comment TEXT,
        created_at TEXT NOT NULL
    )
    """,
)

TABLES_DROP_ORDER = (
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
)

CURRENCY_COLUMNS = (
    ("income_sources", "currency"),
    ("income_entries", "currency"),
    ("budget_categories", "currency"),
    ("budget_entries", "currency"),
    ("savings_goals", "currency"),
    ("savings_entries", "currency"),
)
