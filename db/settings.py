from db.schema import DEFAULT_SETTINGS


def get_setting(key: str, default=None):
    from db.connection import get_db

    with get_db() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = %s", (key,)
        ).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    from db.connection import get_db

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (%s, %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            (key, value),
        )


def seed_settings(conn):
    for key, value in DEFAULT_SETTINGS:
        conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (%s, %s)
            ON CONFLICT (key) DO NOTHING
            """,
            (key, value),
        )
