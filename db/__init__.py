import os

from config import DATABASE_PATH
from db.connection import get_db, get_connection, now_iso, rows_to_dicts
from db.schema import SCHEMA, TABLES_DROP_ORDER
from db.settings import get_setting, seed_settings, set_setting


def init_db():
    with get_db() as conn:
        conn.executescript(SCHEMA)
        seed_settings(conn)


def reset_db():
    """Удалить все данные и пересоздать пустую БД."""
    if os.path.exists(DATABASE_PATH):
        os.remove(DATABASE_PATH)
    init_db()


__all__ = [
    "DATABASE_PATH",
    "get_db",
    "get_connection",
    "get_setting",
    "init_db",
    "now_iso",
    "reset_db",
    "rows_to_dicts",
    "set_setting",
]
