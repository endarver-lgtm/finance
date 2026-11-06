from datetime import date

from db import get_db, now_iso, rows_to_dicts
from services.constants import BASE_CURRENCY, ONE_TIME_INCOME_LABEL
from services.currency import compute_entry_fx, normalize_currency, to_byn
from services.dates import to_iso


def sum_in_range_byn(
    table: str,
    date_col: str,
    start: date,
    end: date,
    extra: str = "",
    params=(),
) -> float:
    """Суммирует amount_byn за период (A1). Если amount_byn пуст, конвертирует на лету."""
    sql = f"""
        SELECT amount, currency, amount_byn FROM {table}
        WHERE {date_col} >= ? AND {date_col} <= ?
    """
    if extra:
        sql += f" AND {extra}"
    with get_db() as conn:
        rows = conn.execute(sql, (to_iso(start), to_iso(end), *params)).fetchall()
    return round(
        sum(
            r["amount_byn"] if ("amount_byn" in r.keys() and r["amount_byn"] is not None)
            else to_byn(r["amount"], r["currency"] if "currency" in r.keys() else "BYN")
            for r in rows
        ),
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
                SELECT id, amount, currency, amount_byn, date, comment FROM income_entries
                WHERE source_id = ? AND date >= ? AND date <= ?
                ORDER BY date DESC, id DESC
                """,
                (s["id"], to_iso(start), to_iso(end)),
            ).fetchall()
            s["entries"] = rows_to_dicts(period_rows)
            s["fact"] = round(
                sum(
                    e["amount_byn"] if e.get("amount_byn") is not None
                    else to_byn(e["amount"], e["currency"])
                    for e in s["entries"]
                ),
                2,
            )
            all_rows = conn.execute(
                """
                SELECT amount, currency, amount_byn FROM income_entries
                WHERE source_id = ?
                """,
                (s["id"],),
            ).fetchall()
            s["total_fact"] = round(
                sum(
                    e["amount_byn"] if e.get("amount_byn") is not None
                    else to_byn(e["amount"], e["currency"])
                    for e in all_rows
                ),
                2,
            )
    return sources


def list_orphan_income_entries(start: date, end: date) -> list[dict]:
    with get_db() as conn:
        return rows_to_dicts(
            conn.execute(
                """
                SELECT id, amount, currency, amount_byn, date, comment FROM income_entries
                WHERE source_id IS NULL AND date >= ? AND date <= ?
                ORDER BY date DESC, id DESC
                """,
                (to_iso(start), to_iso(end)),
            ).fetchall()
        )


def list_income_sources() -> list[dict]:
    with get_db() as conn:
        return rows_to_dicts(
            conn.execute("SELECT * FROM income_sources ORDER BY active DESC, name ASC").fetchall()
        )


def sum_orphan_income_byn(start: date, end: date) -> float:
    """Поступления без привязки к источнику (кнопка «Разовый доход»)."""
    return sum_in_range_byn(
        "income_entries",
        "date",
        start,
        end,
        "source_id IS NULL",
    )


def create_income_source(name, type_, planned_amount, frequency, currency, expected_date=None, pay_days=None):
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO income_sources
                (name, type, planned_amount, currency, frequency, active, expected_date, pay_days, created_at)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)
            """,
            (
                name.strip(),
                type_,
                float(planned_amount or 0),
                normalize_currency(currency),
                frequency,
                expected_date,
                pay_days,
                now_iso(),
            ),
        )
        return cursor.lastrowid


def update_income_source(source_id: int, name: str, planned_amount: float, currency: str, type_: str, frequency: str, expected_date=None, pay_days=None):
    with get_db() as conn:
        conn.execute(
            """
            UPDATE income_sources
            SET name = ?, planned_amount = ?, currency = ?, type = ?, frequency = ?, expected_date = ?, pay_days = ?
            WHERE id = ?
            """,
            (
                name.strip(),
                float(planned_amount or 0),
                normalize_currency(currency),
                type_,
                frequency,
                expected_date,
                pay_days,
                source_id,
            ),
        )


def delete_income_source(source_id: int) -> bool:
    with get_db() as conn:
        conn.execute("UPDATE income_entries SET source_id = NULL WHERE source_id = ?", (source_id,))
        res = conn.execute("DELETE FROM income_sources WHERE id = ?", (source_id,))
        return res.rowcount > 0


def create_income_entry(source_id, amount, entry_date, comment, currency, amount_byn_custom=None):
    cur = normalize_currency(currency)
    amt = float(amount or 0)
    r_usd, r_eur, byn_val, fx_src = compute_entry_fx(amt, cur, amount_byn_custom)
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO income_entries
                (source_id, amount, currency, date, comment, rate_usd, rate_eur, amount_byn, fx_source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                amt,
                cur,
                entry_date,
                comment,
                r_usd,
                r_eur,
                byn_val,
                fx_src,
                now_iso(),
            ),
        )
        row = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
        return row["id"] if row else cursor.lastrowid


def update_income_entry(entry_id: int, source_id: int | None, amount: float, currency: str, entry_date: str, comment: str, amount_byn_custom=None):
    cur = normalize_currency(currency)
    amt = float(amount or 0)
    r_usd, r_eur, byn_val, fx_src = compute_entry_fx(amt, cur, amount_byn_custom)
    with get_db() as conn:
        conn.execute(
            """
            UPDATE income_entries
            SET source_id = ?, amount = ?, currency = ?, date = ?, comment = ?,
                rate_usd = ?, rate_eur = ?, amount_byn = ?, fx_source = ?
            WHERE id = ?
            """,
            (source_id, amt, cur, entry_date, comment, r_usd, r_eur, byn_val, fx_src, entry_id),
        )


def delete_income_entry(entry_id: int) -> bool:
    with get_db() as conn:
        res = conn.execute("DELETE FROM income_entries WHERE id = ?", (entry_id,))
        return res.rowcount > 0


# --- Budget ---

def list_budget_categories():
    with get_db() as conn:
        return rows_to_dicts(
            conn.execute(
                "SELECT * FROM budget_categories ORDER BY is_system ASC, track_only ASC, name ASC"
            ).fetchall()
        )


def create_budget_category(name, planned_amount, period, currency, is_fixed: int | None = None):
    # If not explicitly specified, default is_fixed: month -> 1, week -> 0 (A3)
    if is_fixed is None:
        is_fixed = 1 if period == "month" else 0
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO budget_categories
                (name, planned_amount, currency, period, is_fixed, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name.strip(), float(planned_amount or 0), normalize_currency(currency), period, int(is_fixed), now_iso()),
        )
        return cursor.lastrowid


def update_budget_category(category_id: int, name: str, planned_amount: float, period: str, currency: str, is_fixed: int | None = None):
    with get_db() as conn:
        cat = conn.execute("SELECT is_system, track_only FROM budget_categories WHERE id = ?", (category_id,)).fetchone()
        if not cat:
            raise ValueError("Категория не найдена")
        
        fixed_val = is_fixed if is_fixed is not None else (1 if period == "month" else 0)
        if cat["is_system"] or cat["track_only"]:
            conn.execute(
                """
                UPDATE budget_categories
                SET planned_amount = ?, currency = ?, period = ?, is_fixed = 0
                WHERE id = ?
                """,
                (float(planned_amount or 0), normalize_currency(currency), period, category_id),
            )
        else:
            conn.execute(
                """
                UPDATE budget_categories
                SET name = ?, planned_amount = ?, currency = ?, period = ?, is_fixed = ?
                WHERE id = ?
                """,
                (name.strip(), float(planned_amount or 0), normalize_currency(currency), period, int(fixed_val), category_id),
            )


def delete_budget_category(category_id: int) -> bool:
    with get_db() as conn:
        cat = conn.execute("SELECT is_system, track_only, name FROM budget_categories WHERE id = ?", (category_id,)).fetchone()
        if not cat:
            return False
        if cat["is_system"] or cat["track_only"] or cat["name"] == "Неучтёнка":
            raise ValueError("Системную категорию «Неучтёнка» нельзя удалить")
        
        system_cat = conn.execute("SELECT id FROM budget_categories WHERE is_system = 1 OR track_only = 1 LIMIT 1").fetchone()
        if system_cat:
            conn.execute("UPDATE budget_entries SET category_id = ? WHERE category_id = ?", (system_cat["id"], category_id))
        else:
            conn.execute("DELETE FROM budget_entries WHERE category_id = ?", (category_id,))
            
        conn.execute("DELETE FROM budget_categories WHERE id = ?", (category_id,))
    return True


def create_budget_entry(category_id, amount, entry_date, comment, currency, amount_byn_custom=None, from_goal_id=None):
    cur = normalize_currency(currency)
    amt = float(amount or 0)
    r_usd, r_eur, byn_val, fx_src = compute_entry_fx(amt, cur, amount_byn_custom)
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO budget_entries
                (category_id, amount, currency, date, comment, from_goal_id, rate_usd, rate_eur, amount_byn, fx_source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                category_id,
                amt,
                cur,
                entry_date,
                comment,
                from_goal_id,
                r_usd,
                r_eur,
                byn_val,
                fx_src,
                now_iso(),
            ),
        )
        row = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
        return row["id"] if row else cursor.lastrowid


def update_budget_entry(entry_id: int, category_id: int, amount: float, currency: str, entry_date: str, comment: str, amount_byn_custom=None):
    cur = normalize_currency(currency)
    amt = float(amount or 0)
    r_usd, r_eur, byn_val, fx_src = compute_entry_fx(amt, cur, amount_byn_custom)
    with get_db() as conn:
        conn.execute(
            """
            UPDATE budget_entries
            SET category_id = ?, amount = ?, currency = ?, date = ?, comment = ?,
                rate_usd = ?, rate_eur = ?, amount_byn = ?, fx_source = ?
            WHERE id = ?
            """,
            (category_id, amt, cur, entry_date, comment, r_usd, r_eur, byn_val, fx_src, entry_id),
        )
        conn.execute(
            """
            UPDATE debts
            SET amount = ?, currency = ?, date = ?, comment = ?,
                rate_usd = ?, rate_eur = ?, amount_byn = ?, fx_source = ?
            WHERE budget_entry_id = ?
            """,
            (amt, cur, entry_date, comment, r_usd, r_eur, byn_val, fx_src, entry_id),
        )
        conn.execute(
            """
            UPDATE savings_entries
            SET amount = ?, currency = ?, date = ?, comment = ?,
                rate_usd = ?, rate_eur = ?, amount_byn = ?, fx_source = ?
            WHERE budget_entry_id = ?
            """,
            (amt, cur, entry_date, comment, r_usd, r_eur, byn_val, fx_src, entry_id),
        )


def delete_budget_entry(entry_id: int) -> bool:
    with get_db() as conn:
        entry = conn.execute("SELECT id FROM budget_entries WHERE id = ?", (entry_id,)).fetchone()
        if not entry:
            return False
        conn.execute("DELETE FROM debts WHERE budget_entry_id = ?", (entry_id,))
        conn.execute("DELETE FROM savings_entries WHERE budget_entry_id = ?", (entry_id,))
        conn.execute("DELETE FROM budget_entries WHERE id = ?", (entry_id,))
    return True


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
    from services.savings import goal_balance

    return goal_balance(goal_id, goal_currency)


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


def create_savings_goal(name, type_, target_amount, deadline, currency):
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO savings_goals
                (name, type, target_amount, currency, deadline, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                name.strip(),
                type_,
                float(target_amount or 0),
                normalize_currency(currency),
                deadline,
                now_iso(),
            ),
        )
        return cursor.lastrowid


def update_savings_goal(goal_id: int, name: str, target_amount: float, currency: str, deadline: str | None, type_: str):
    with get_db() as conn:
        conn.execute(
            """
            UPDATE savings_goals
            SET name = ?, target_amount = ?, currency = ?, deadline = ?, type = ?
            WHERE id = ?
            """,
            (name.strip(), float(target_amount or 0), normalize_currency(currency), deadline, type_, goal_id),
        )


def delete_savings_goal(goal_id: int) -> bool:
    with get_db() as conn:
        conn.execute(
            """
            DELETE FROM budget_entries
            WHERE id IN (
                SELECT budget_entry_id FROM savings_entries
                WHERE goal_id = ? AND budget_entry_id IS NOT NULL
            )
            """,
            (goal_id,),
        )
        conn.execute("DELETE FROM savings_entries WHERE goal_id = ?", (goal_id,))
        res = conn.execute("DELETE FROM savings_goals WHERE id = ?", (goal_id,))
        return res.rowcount > 0


def create_savings_entry(goal_id, amount, entry_date, comment, currency, kind='deposit', budget_entry_id=None):
    cur = normalize_currency(currency)
    amt = float(amount or 0)
    r_usd, r_eur, byn_val, fx_src = compute_entry_fx(amt, cur)
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO savings_entries
                (goal_id, amount, currency, date, comment, kind, budget_entry_id, rate_usd, rate_eur, amount_byn, fx_source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                goal_id,
                amt,
                cur,
                entry_date,
                comment,
                kind,
                budget_entry_id,
                r_usd,
                r_eur,
                byn_val,
                fx_src,
                now_iso(),
            ),
        )
        row = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
        return row["id"] if row else cursor.lastrowid


def update_savings_entry(entry_id: int, amount: float, currency: str, entry_date: str, comment: str):
    cur = normalize_currency(currency)
    amt = float(amount or 0)
    r_usd, r_eur, byn_val, fx_src = compute_entry_fx(amt, cur)
    with get_db() as conn:
        entry = conn.execute("SELECT budget_entry_id FROM savings_entries WHERE id = ?", (entry_id,)).fetchone()
        if not entry:
            raise ValueError("Запись накоплений не найдена")
        conn.execute(
            """
            UPDATE savings_entries
            SET amount = ?, currency = ?, date = ?, comment = ?,
                rate_usd = ?, rate_eur = ?, amount_byn = ?, fx_source = ?
            WHERE id = ?
            """,
            (amt, cur, entry_date, comment, r_usd, r_eur, byn_val, fx_src, entry_id),
        )
        if entry["budget_entry_id"]:
            conn.execute(
                """
                UPDATE budget_entries
                SET amount = ?, currency = ?, date = ?, comment = ?,
                    rate_usd = ?, rate_eur = ?, amount_byn = ?, fx_source = ?
                WHERE id = ?
                """,
                (amt, cur, entry_date, comment, r_usd, r_eur, byn_val, fx_src, entry["budget_entry_id"]),
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
        try:
            for row in conn.execute("SELECT DISTINCT person FROM debts"):
                if row["person"]:
                    names.add(row["person"])
        except Exception:
            pass
    return sorted(names)
