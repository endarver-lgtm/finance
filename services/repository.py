from datetime import date

from db import get_db, now_iso, rows_to_dicts
from services.constants import ONE_TIME_INCOME_LABEL
from services.dates import to_iso


def sum_in_range(
    table: str,
    amount_col: str,
    date_col: str,
    start: date,
    end: date,
    extra: str = "",
    params=(),
) -> float:
    sql = f"""
        SELECT COALESCE(SUM({amount_col}), 0) AS total
        FROM {table}
        WHERE {date_col} >= ? AND {date_col} <= ?
    """
    if extra:
        sql += f" AND {extra}"
    with get_db() as conn:
        row = conn.execute(sql, (to_iso(start), to_iso(end), *params)).fetchone()
    return float(row["total"])


# --- Income ---

def list_income_sources_with_fact(start: date, end: date):
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT s.*, COALESCE(SUM(e.amount), 0) AS fact
            FROM income_sources s
            LEFT JOIN income_entries e
              ON e.source_id = s.id
             AND e.date >= ? AND e.date <= ?
            GROUP BY s.id
            ORDER BY s.active DESC, s.name
            """,
            (to_iso(start), to_iso(end)),
        ).fetchall()
    return rows_to_dicts(rows)


def create_income_source(name, type_, planned_amount, frequency):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO income_sources
                (name, type, planned_amount, frequency, active, created_at)
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (name, type_, planned_amount, frequency, now_iso()),
        )


def create_income_entry(source_id, amount, entry_date, comment):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO income_entries (source_id, amount, date, comment, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (source_id, amount, entry_date, comment, now_iso()),
        )


# --- Budget ---

def list_budget_categories():
    with get_db() as conn:
        return rows_to_dicts(
            conn.execute(
                "SELECT * FROM budget_categories ORDER BY name"
            ).fetchall()
        )


def list_budget_entries(category_id: int):
    with get_db() as conn:
        return rows_to_dicts(
            conn.execute(
                """
                SELECT * FROM budget_entries
                WHERE category_id = ?
                ORDER BY date DESC, id DESC
                """,
                (category_id,),
            ).fetchall()
        )


def create_budget_category(name, planned_amount, period):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO budget_categories (name, planned_amount, period, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (name, planned_amount, period, now_iso()),
        )


def create_budget_entry(category_id, amount, entry_date, comment):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO budget_entries
                (category_id, amount, date, comment, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (category_id, amount, entry_date, comment, now_iso()),
        )


# --- Savings ---

def list_savings_goals():
    with get_db() as conn:
        return rows_to_dicts(
            conn.execute(
                "SELECT * FROM savings_goals ORDER BY type, name"
            ).fetchall()
        )


def sum_savings_for_goal(goal_id: int) -> float:
    with get_db() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS t FROM savings_entries WHERE goal_id = ?",
            (goal_id,),
        ).fetchone()
    return float(row["t"])


def list_savings_entries(goal_id: int):
    with get_db() as conn:
        return rows_to_dicts(
            conn.execute(
                """
                SELECT * FROM savings_entries
                WHERE goal_id = ?
                ORDER BY date DESC, id DESC
                """,
                (goal_id,),
            ).fetchall()
        )


def create_savings_goal(name, type_, target_amount, deadline):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO savings_goals
                (name, type, target_amount, deadline, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, type_, target_amount, deadline, now_iso()),
        )


def create_savings_entry(goal_id, amount, entry_date, comment):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO savings_entries
                (goal_id, amount, date, comment, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (goal_id, amount, entry_date, comment, now_iso()),
        )


# --- History filters ---

def list_history_category_names() -> list[str]:
    names = {ONE_TIME_INCOME_LABEL}
    with get_db() as conn:
        for row in conn.execute("SELECT name FROM income_sources"):
            names.add(row["name"])
        for row in conn.execute("SELECT name FROM budget_categories"):
            names.add(row["name"])
        for row in conn.execute("SELECT name FROM savings_goals"):
            names.add(row["name"])
    return sorted(names)
