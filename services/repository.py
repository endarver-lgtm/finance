from datetime import date

from db import get_db, now_iso, rows_to_dicts
from services.constants import BASE_CURRENCY, ONE_TIME_INCOME_LABEL
from services.currency import normalize_currency, to_byn
from services.dates import to_iso


def sum_in_range_byn(
    table: str,
    date_col: str,
    start: date,
    end: date,
    extra: str = "",
    params=(),
) -> float:
    sql = f"""
        SELECT amount, currency FROM {table}
        WHERE {date_col} >= %s AND {date_col} <= %s
    """
    if extra:
        sql += f" AND {extra}"
    with get_db() as conn:
        rows = conn.execute(sql, (to_iso(start), to_iso(end), *params)).fetchall()
    return round(
        sum(to_byn(r["amount"], r["currency"] if "currency" in r.keys() else "BYN") for r in rows),
        2,
    )


# --- Income ---

def list_income_sources_with_fact(start: date, end: date, *, active_only: bool = True):
    with get_db() as conn:
        sql = "SELECT * FROM income_sources"
        if active_only:
            sql += " WHERE active = 1"
        sql += " ORDER BY name"
        sources = rows_to_dicts(conn.execute(sql).fetchall())
        for s in sources:
            period_rows = conn.execute(
                """
                SELECT amount, currency FROM income_entries
                WHERE source_id = %s AND date >= %s AND date <= %s
                """,
                (s["id"], to_iso(start), to_iso(end)),
            ).fetchall()
            s["fact"] = round(
                sum(to_byn(e["amount"], e["currency"]) for e in period_rows), 2
            )
            all_rows = conn.execute(
                """
                SELECT amount, currency FROM income_entries
                WHERE source_id = %s
                """,
                (s["id"],),
            ).fetchall()
            s["total_fact"] = round(
                sum(to_byn(e["amount"], e["currency"]) for e in all_rows), 2
            )
    return sources


def sum_orphan_income_byn(start: date, end: date) -> float:
    """Поступления без привязки к источнику (кнопка «Разовый доход»)."""
    return sum_in_range_byn(
        "income_entries",
        "date",
        start,
        end,
        "source_id IS NULL",
    )


def create_income_source(name, type_, planned_amount, frequency, currency):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO income_sources
                (name, type, planned_amount, currency, frequency, active, created_at)
            VALUES (%s, %s, %s, %s, %s, 1, %s)
            """,
            (name, type_, planned_amount, normalize_currency(currency), frequency, now_iso()),
        )


def create_income_entry(source_id, amount, entry_date, comment, currency):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO income_entries
                (source_id, amount, currency, date, comment, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                source_id,
                amount,
                normalize_currency(currency),
                entry_date,
                comment,
                now_iso(),
            ),
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
                WHERE category_id = %s
                ORDER BY date DESC, id DESC
                """,
                (category_id,),
            ).fetchall()
        )


def create_budget_category(name, planned_amount, period, currency):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO budget_categories
                (name, planned_amount, currency, period, created_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (name, planned_amount, normalize_currency(currency), period, now_iso()),
        )


def create_budget_entry(category_id, amount, entry_date, comment, currency):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO budget_entries
                (category_id, amount, currency, date, comment, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                category_id,
                amount,
                normalize_currency(currency),
                entry_date,
                comment,
                now_iso(),
            ),
        )


# --- Savings ---

def list_savings_goals():
    with get_db() as conn:
        return rows_to_dicts(
            conn.execute(
                "SELECT * FROM savings_goals ORDER BY type, name"
            ).fetchall()
        )


def sum_savings_for_goal(goal_id: int, goal_currency: str | None = None) -> float:
    """Накоплено в валюте цели."""
    from services.currency import convert

    goal_currency = normalize_currency(goal_currency or BASE_CURRENCY)
    with get_db() as conn:
        rows = conn.execute(
            "SELECT amount, currency FROM savings_entries WHERE goal_id = %s",
            (goal_id,),
        ).fetchall()
    return round(
        sum(convert(r["amount"], r["currency"], goal_currency) for r in rows), 2
    )


def list_savings_entries(goal_id: int):
    with get_db() as conn:
        return rows_to_dicts(
            conn.execute(
                """
                SELECT * FROM savings_entries
                WHERE goal_id = %s
                ORDER BY date DESC, id DESC
                """,
                (goal_id,),
            ).fetchall()
        )


def create_savings_goal(name, type_, target_amount, deadline, currency):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO savings_goals
                (name, type, target_amount, currency, deadline, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                name,
                type_,
                target_amount,
                normalize_currency(currency),
                deadline,
                now_iso(),
            ),
        )


def create_savings_entry(goal_id, amount, entry_date, comment, currency):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO savings_entries
                (goal_id, amount, currency, date, comment, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                goal_id,
                amount,
                normalize_currency(currency),
                entry_date,
                comment,
                now_iso(),
            ),
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
