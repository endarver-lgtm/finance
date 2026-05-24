from db.connection import get_db
from db.schema import DEFAULT_SETTINGS


def get_setting(key: str, default=None):
    with get_db() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )


def seed_settings(conn):
    for key, value in DEFAULT_SETTINGS:
        exists = conn.execute(
            "SELECT 1 FROM settings WHERE key = ?", (key,)
        ).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
    conn.execute("UPDATE settings SET value = 'BYN' WHERE key = 'currency'")
