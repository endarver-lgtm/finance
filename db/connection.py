import sqlite3
from contextlib import contextmanager
from datetime import datetime

from config import DATABASE_PATH


class Row(dict):
    """Dictionary-like row that also supports integer indexing (e.g. row[0])."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._keys = list(self.keys())

    def __getitem__(self, key):
        if isinstance(key, int):
            return super().__getitem__(self._keys[key])
        return super().__getitem__(key)


def _row_factory(cursor, row):
    col_names = [col[0] for col in cursor.description]
    return Row(zip(col_names, row))


def _normalize_sql(sql: str) -> str:
    if "%s" in sql:
        return sql.replace("%s", "?")
    return sql


class SqliteConnection:
    """Wrapper around sqlite3.Connection with auto %s -> ? translation and dict rows."""

    def __init__(self, raw: sqlite3.Connection):
        self._raw = raw

    def execute(self, sql: str, params=None):
        sql = _normalize_sql(sql)
        if params is not None:
            return self._raw.execute(sql, params)
        return self._raw.execute(sql)

    def executemany(self, sql: str, params_seq):
        sql = _normalize_sql(sql)
        return self._raw.executemany(sql, params_seq)

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        self._raw.close()


def get_connection() -> SqliteConnection:
    raw = sqlite3.connect(DATABASE_PATH)
    raw.row_factory = _row_factory
    raw.execute("PRAGMA foreign_keys = ON")
    return SqliteConnection(raw)


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
