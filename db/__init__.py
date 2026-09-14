from db.connection import get_db, get_connection, now_iso, rows_to_dicts
from db.migrate import migrate_db
from db.schema import SCHEMA_STATEMENTS, TABLES_DROP_ORDER
from db.settings import get_setting, seed_settings, set_setting


def init_db():
    with get_db() as conn:
        for statement in SCHEMA_STATEMENTS:
            conn.execute(statement)
        migrate_db(conn)
        seed_settings(conn)


def reset_db():
    """Drop all app tables and recreate empty schema with default settings."""
    with get_db() as conn:
        for table in TABLES_DROP_ORDER:
            conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    init_db()


__all__ = [
    "get_db",
    "get_connection",
    "get_setting",
    "init_db",
    "now_iso",
    "reset_db",
    "rows_to_dicts",
    "set_setting",
]
