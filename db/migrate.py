from db.connection import now_iso
from db.schema import CURRENCY_COLUMNS

ADDITIONAL_COLUMNS = (
    ("savings_entries", "kind", "TEXT NOT NULL DEFAULT 'deposit'"),
    ("savings_entries", "budget_entry_id", "INTEGER"),
    ("budget_entries", "from_goal_id", "INTEGER"),
    ("budget_categories", "is_system", "INTEGER NOT NULL DEFAULT 0"),
    ("budget_categories", "track_only", "INTEGER NOT NULL DEFAULT 0"),
)


def _table_exists(conn, table: str) -> bool:
    try:
        r = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        if r:
            return True
    except Exception:
        pass
    try:
        r = conn.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = ?",
            (table,),
        ).fetchone()
        return bool(r)
    except Exception:
        return False


def _get_columns(conn, table: str) -> list[str]:
    try:
        return [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    except Exception:
        try:
            rows = conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
                (table,),
            ).fetchall()
            return [r["column_name"] for r in rows]
        except Exception:
            return []


def _add_column_if_missing(conn, table: str, column: str, col_def: str):
    if not _table_exists(conn, table):
        return
    cols = _get_columns(conn, table)
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")


def ensure_system_categories(conn):
    if not _table_exists(conn, "budget_categories"):
        return
    existing = conn.execute(
        "SELECT id FROM budget_categories WHERE name = ?",
        ("Неучтёнка",),
    ).fetchone()
    if not existing:
        conn.execute(
            """
            INSERT INTO budget_categories (name, planned_amount, currency, period, is_system, track_only, created_at)
            VALUES (?, 0, 'BYN', 'month', 1, 1, ?)
            """,
            ("Неучтёнка", now_iso()),
        )
    else:
        conn.execute(
            "UPDATE budget_categories SET is_system = 1, track_only = 1 WHERE name = ?",
            ("Неучтёнка",),
        )


def migrate_db(conn):
    """Add currency and feature columns on older DBs that were created without them."""
    for table, column in CURRENCY_COLUMNS:
        _add_column_if_missing(conn, table, column, "TEXT NOT NULL DEFAULT 'BYN'")

    for table, column, col_def in ADDITIONAL_COLUMNS:
        _add_column_if_missing(conn, table, column, col_def)

    if _table_exists(conn, "savings_entries"):
        cols = _get_columns(conn, "savings_entries")
        if "kind" in cols:
            conn.execute(
                "UPDATE savings_entries SET kind = 'deposit' WHERE kind IS NULL OR kind = ''"
            )

    ensure_system_categories(conn)

