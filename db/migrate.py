from db.connection import now_iso
from db.schema import CURRENCY_COLUMNS

ADDITIONAL_COLUMNS = (
    ("savings_entries", "kind", "TEXT NOT NULL DEFAULT 'deposit'"),
    ("savings_entries", "budget_entry_id", "INTEGER"),
    ("budget_entries", "from_goal_id", "INTEGER"),
    ("budget_categories", "is_system", "INTEGER NOT NULL DEFAULT 0"),
    ("budget_categories", "track_only", "INTEGER NOT NULL DEFAULT 0"),
    # A1 & A3: FX rates, converted BYN, fx_source and fixed expense flags
    ("budget_categories", "is_fixed", "INTEGER NOT NULL DEFAULT 0"),
    ("budget_entries", "rate_usd", "REAL"),
    ("budget_entries", "rate_eur", "REAL"),
    ("budget_entries", "amount_byn", "REAL"),
    ("budget_entries", "fx_source", "TEXT DEFAULT 'entry'"),
    ("income_entries", "rate_usd", "REAL"),
    ("income_entries", "rate_eur", "REAL"),
    ("income_entries", "amount_byn", "REAL"),
    ("income_entries", "fx_source", "TEXT DEFAULT 'entry'"),
    ("savings_entries", "rate_usd", "REAL"),
    ("savings_entries", "rate_eur", "REAL"),
    ("savings_entries", "amount_byn", "REAL"),
    ("savings_entries", "fx_source", "TEXT DEFAULT 'entry'"),
    ("debts", "rate_usd", "REAL"),
    ("debts", "rate_eur", "REAL"),
    ("debts", "amount_byn", "REAL"),
    ("debts", "fx_source", "TEXT DEFAULT 'entry'"),
    # J1: Debt offsets and expense links
    ("debts", "category_id", "INTEGER"),
    ("debts", "offset_date", "TEXT"),
    ("debts", "expense_id", "INTEGER"),
    ("debts", "source", "TEXT NOT NULL DEFAULT 'manual'"),
    # A2: Balance checks fx effect
    ("balance_checks", "rate_usd", "REAL"),
    ("balance_checks", "rate_eur", "REAL"),
    ("balance_checks", "fx_effect_byn", "REAL DEFAULT 0"),
    # D2 & D3: Income sources expected date and payout days
    ("income_sources", "expected_date", "TEXT"),
    ("income_sources", "pay_days", "TEXT"),
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
            INSERT INTO budget_categories (name, planned_amount, currency, period, is_system, track_only, is_fixed, created_at)
            VALUES (?, 0, 'BYN', 'month', 1, 1, 0, ?)
            """,
            ("Неучтёнка", now_iso()),
        )
    else:
        conn.execute(
            "UPDATE budget_categories SET is_system = 1, track_only = 1 WHERE name = ?",
            ("Неучтёнка",),
        )


def _backfill_fx_and_flags(conn):
    """Backfill amount_byn, historical fx rates, is_fixed and expected_date."""
    # 1. Get current rates from settings for backfilling old entries
    usd_rate = 3.27
    eur_rate = 3.55
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = 'usd_rate'").fetchone()
        if row and row["value"]:
            usd_rate = float(row["value"])
    except Exception:
        pass
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = 'eur_rate'").fetchone()
        if row and row["value"]:
            eur_rate = float(row["value"])
    except Exception:
        pass

    # 2. Backfill is_fixed in budget_categories (A3)
    # period='month' -> 1, period='week' -> 0, track_only=1 -> 0
    if _table_exists(conn, "budget_categories"):
        conn.execute(
            """
            UPDATE budget_categories
            SET is_fixed = 1
            WHERE period = 'month' AND is_system = 0 AND track_only = 0 AND (is_fixed IS NULL OR is_fixed = 0)
            """
        )
        conn.execute(
            """
            UPDATE budget_categories
            SET is_fixed = 0
            WHERE period = 'week' OR is_system = 1 OR track_only = 1
            """
        )

    # 3. Backfill fx columns for transaction tables (A1)
    for table in ("budget_entries", "income_entries", "savings_entries", "debts"):
        if not _table_exists(conn, table):
            continue

        # BYN entries: amount_byn = amount, rates filled, fx_source = 'backfill'
        conn.execute(
            f"""
            UPDATE {table}
            SET amount_byn = amount,
                rate_usd = ?,
                rate_eur = ?,
                fx_source = 'backfill'
            WHERE (currency = 'BYN' OR currency IS NULL)
              AND (amount_byn IS NULL OR amount_byn = 0)
            """,
            (usd_rate, eur_rate),
        )

        # USD entries
        conn.execute(
            f"""
            UPDATE {table}
            SET amount_byn = round(amount * ?, 2),
                rate_usd = ?,
                rate_eur = ?,
                fx_source = 'backfill'
            WHERE currency = 'USD'
              AND (amount_byn IS NULL OR amount_byn = 0)
            """,
            (usd_rate, usd_rate, eur_rate),
        )

        # EUR entries
        conn.execute(
            f"""
            UPDATE {table}
            SET amount_byn = round(amount * ?, 2),
                rate_usd = ?,
                rate_eur = ?,
                fx_source = 'backfill'
            WHERE currency = 'EUR'
              AND (amount_byn IS NULL OR amount_byn = 0)
            """,
            (eur_rate, usd_rate, eur_rate),
        )

    # 4. Backfill income_sources expected_date (D2)
    if _table_exists(conn, "income_sources"):
        conn.execute(
            """
            UPDATE income_sources
            SET expected_date = substr(created_at, 1, 10)
            WHERE type = 'one_time' AND (expected_date IS NULL OR expected_date = '')
            """
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

    if _table_exists(conn, "debts"):
        conn.execute("CREATE INDEX IF NOT EXISTS idx_debts_category_offset ON debts(category_id, offset_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_debts_expense_id ON debts(expense_id)")

    ensure_system_categories(conn)
    _backfill_fx_and_flags(conn)
