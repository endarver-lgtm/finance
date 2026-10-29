-- Finance Tracker — схема для Supabase (Postgres)
-- Можно вставить в: Supabase → SQL Editor → New query → Run
-- Приложение также создаёт таблицы само при первом запуске (CREATE IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS income_sources (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('regular', 'one_time')),
    planned_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'BYN',
    frequency TEXT NOT NULL CHECK (frequency IN ('weekly', 'monthly', 'one_time')),
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS income_entries (
    id SERIAL PRIMARY KEY,
    source_id INTEGER REFERENCES income_sources(id) ON DELETE SET NULL,
    amount DOUBLE PRECISION NOT NULL,
    currency TEXT NOT NULL DEFAULT 'BYN',
    date TEXT NOT NULL,
    comment TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS budget_categories (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    planned_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'BYN',
    period TEXT NOT NULL CHECK (period IN ('week', 'month')),
    is_system INTEGER NOT NULL DEFAULT 0,
    track_only INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS budget_entries (
    id SERIAL PRIMARY KEY,
    category_id INTEGER NOT NULL REFERENCES budget_categories(id) ON DELETE CASCADE,
    amount DOUBLE PRECISION NOT NULL,
    currency TEXT NOT NULL DEFAULT 'BYN',
    date TEXT NOT NULL,
    comment TEXT,
    from_goal_id INTEGER REFERENCES savings_goals(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS savings_goals (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('want', 'reserve', 'big')),
    target_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'BYN',
    deadline TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS savings_entries (
    id SERIAL PRIMARY KEY,
    goal_id INTEGER NOT NULL REFERENCES savings_goals(id) ON DELETE CASCADE,
    amount DOUBLE PRECISION NOT NULL,
    currency TEXT NOT NULL DEFAULT 'BYN',
    date TEXT NOT NULL,
    comment TEXT,
    kind TEXT NOT NULL DEFAULT 'deposit',
    budget_entry_id INTEGER REFERENCES budget_entries(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS debts (
    id SERIAL PRIMARY KEY,
    person TEXT NOT NULL,
    kind TEXT NOT NULL,
    amount DOUBLE PRECISION NOT NULL,
    currency TEXT NOT NULL DEFAULT 'BYN',
    date TEXT NOT NULL,
    comment TEXT,
    budget_entry_id INTEGER REFERENCES budget_entries(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_debts_person_date ON debts(person, date);
CREATE INDEX IF NOT EXISTS idx_debts_budget_entry ON debts(budget_entry_id);

CREATE TABLE IF NOT EXISTS balance_checks (
    id SERIAL PRIMARY KEY,
    date TEXT NOT NULL,
    real_byn DOUBLE PRECISION NOT NULL,
    expected_byn DOUBLE PRECISION,
    diff_byn DOUBLE PRECISION,
    real_breakdown TEXT,
    savings_in_check INTEGER NOT NULL DEFAULT 1,
    adjust_expense_id INTEGER REFERENCES budget_entries(id) ON DELETE SET NULL,
    adjust_income_id INTEGER REFERENCES income_entries(id) ON DELETE SET NULL,
    comment TEXT,
    created_at TEXT NOT NULL
);

INSERT INTO settings (key, value) VALUES
    ('currency', 'BYN'),
    ('usd_rate', '3.27'),
    ('eur_rate', '3.55'),
    ('savings_in_check', '1'),
    ('default_debt_person', 'Кент')
ON CONFLICT (key) DO NOTHING;

INSERT INTO budget_categories (name, planned_amount, currency, period, is_system, track_only, created_at)
SELECT 'Неучтёнка', 0, 'BYN', 'month', 1, 1, TO_CHAR(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS')
WHERE NOT EXISTS (SELECT 1 FROM budget_categories WHERE name = 'Неучтёнка');

