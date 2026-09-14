from db.schema import CURRENCY_COLUMNS


def migrate_db(conn):
    """Add currency columns on older DBs that were created without them."""
    for table, column in CURRENCY_COLUMNS:
        exists = conn.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
              AND column_name = %s
            """,
            (table, column),
        ).fetchone()
        if not exists:
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} TEXT NOT NULL DEFAULT 'BYN'"
            )
