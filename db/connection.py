from contextlib import contextmanager
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor

from config import DATABASE_URL


class PgConnection:
    """Thin wrapper so call sites can use sqlite-style conn.execute(...).fetchall()."""

    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql, params=None):
        cur = self._raw.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql, params if params is not None else ())
        return cur

    def executemany(self, sql, params_seq):
        cur = self._raw.cursor(cursor_factory=RealDictCursor)
        cur.executemany(sql, params_seq)
        return cur

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        self._raw.close()


def _connect_url() -> str:
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set. Add it to .env (local) or Render environment "
            "(Supabase → Project Settings → Database → Connection string)."
        )
    url = DATABASE_URL
    # Supabase (and most cloud Postgres) require TLS.
    local = "localhost" in url or "127.0.0.1" in url
    if not local and "sslmode=" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return url


def get_connection() -> PgConnection:
    raw = psycopg2.connect(_connect_url(), connect_timeout=15)
    raw.autocommit = False
    return PgConnection(raw)


@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")


def rows_to_dicts(rows):
    return [dict(r) for r in rows]
