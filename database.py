import os
from contextlib import contextmanager
from datetime import datetime, timezone

import config  # noqa: F401 — загрузка .env
import psycopg2
from psycopg2.extras import RealDictCursor

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key VARCHAR(255) PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS income_sources (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(32) NOT NULL CHECK (type IN ('regular', 'one_time')),
    planned_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
    frequency VARCHAR(32) NOT NULL CHECK (frequency IN ('weekly', 'monthly', 'one_time')),
    active SMALLINT NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS income_entries (
    id SERIAL PRIMARY KEY,
    source_id INTEGER REFERENCES income_sources(id) ON DELETE SET NULL,
    amount DOUBLE PRECISION NOT NULL,
    date DATE NOT NULL,
    comment TEXT,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS budget_categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    planned_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
    period VARCHAR(16) NOT NULL CHECK (period IN ('week', 'month')),
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS budget_entries (
    id SERIAL PRIMARY KEY,
    category_id INTEGER NOT NULL REFERENCES budget_categories(id) ON DELETE CASCADE,
    amount DOUBLE PRECISION NOT NULL,
    date DATE NOT NULL,
    comment TEXT,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS savings_goals (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(32) NOT NULL CHECK (type IN ('want', 'reserve', 'big')),
    target_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
    deadline DATE,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS savings_entries (
    id SERIAL PRIMARY KEY,
    goal_id INTEGER NOT NULL REFERENCES savings_goals(id) ON DELETE CASCADE,
    amount DOUBLE PRECISION NOT NULL,
    date DATE NOT NULL,
    comment TEXT,
    created_at TIMESTAMP NOT NULL
);
"""


def get_connection():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is required")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(database_url, sslmode="require")


class DBSession:
    """Обёртка над psycopg2 с API, совместимым с conn.execute().fetchone()."""

    def __init__(self, conn):
        self._conn = conn
        self._cursor = conn.cursor(cursor_factory=RealDictCursor)

    def execute(self, sql, params=None):
        self._cursor.execute(sql, params or ())
        return self._cursor

    def executescript(self, script):
        statements = [s.strip() for s in script.split(";") if s.strip()]
        for statement in statements:
            self._cursor.execute(statement)


@contextmanager
def get_db():
    conn = get_connection()
    session = DBSession(conn)
    try:
        yield session
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        session._cursor.close()
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript(SCHEMA)
        cur = conn.execute("SELECT value FROM settings WHERE key = %s", ("currency",))
        if cur.fetchone() is None:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (%s, %s)",
                ("currency", "€"),
            )


def now_iso():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_setting(key, default=None):
    with get_db() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = %s", (key,)
        ).fetchone()
    return row["value"] if row else default


def set_setting(key, value):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (%s, %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            (key, value),
        )
