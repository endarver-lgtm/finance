from datetime import date
from db import get_db, now_iso, rows_to_dicts
from services.constants import BASE_CURRENCY
from services.currency import compute_entry_fx, convert_at_entry, normalize_currency, to_byn


def goal_balance(goal_id: int, goal_currency: str | None = None) -> float:
    """Накоплено по цели в валюте цели по курсам записей (A1)."""
    with get_db() as conn:
        goal = conn.execute("SELECT currency FROM savings_goals WHERE id = ?", (goal_id,)).fetchone()
        if not goal:
            return 0.0
        target_currency = normalize_currency(goal_currency or goal["currency"])
        rows = conn.execute(
            "SELECT amount, currency, kind, rate_usd, rate_eur, amount_byn FROM savings_entries WHERE goal_id = ?",
            (goal_id,),
        ).fetchall()

    balance = 0.0
    for r in rows:
        kind = r["kind"] if "kind" in r.keys() and r["kind"] else "deposit"
        amt_in_target = convert_at_entry(dict(r), target_currency)
        if kind == "deposit":
            balance += amt_in_target
        elif kind in ("withdraw_spent", "withdraw_free"):
            balance -= amt_in_target

    return round(max(0.0, balance), 2)


def withdraw_from_goal(
    goal_id: int,
    amount: float,
    currency: str,
    entry_date: str,
    purpose: str,
    category_id: int | None = None,
    comment: str | None = None,
) -> dict:
    """Снятие из копилки с проверкой на превышение и созданием связанного расхода при purpose='spent'."""
    amount = round(float(amount), 2)
    if amount <= 0:
        raise ValueError("Сумма снятия должна быть больше нуля")

    if purpose not in ("spent", "free"):
        raise ValueError("Некорректная цель снятия (допустимо: spent или free)")

    currency = normalize_currency(currency)
    r_usd, r_eur, byn_val, fx_src = compute_entry_fx(amount, currency)

    with get_db() as conn:
        goal = conn.execute("SELECT * FROM savings_goals WHERE id = ?", (goal_id,)).fetchone()
        if not goal:
            raise ValueError("Цель накопления не найдена")

        goal_cur = normalize_currency(goal["currency"])
        current_saved = goal_balance(goal_id, goal_cur)
        
        # Check limit in goal's currency using transaction rate
        temp_entry = {"amount": amount, "currency": currency, "rate_usd": r_usd, "rate_eur": r_eur, "amount_byn": byn_val}
        amount_in_goal_cur = convert_at_entry(temp_entry, goal_cur)

        if amount_in_goal_cur > current_saved + 0.005:
            raise ValueError(
                f"Недостаточно средств в копилке: доступно {current_saved} {goal_cur}, "
                f"запрошено {round(amount_in_goal_cur, 2)} {goal_cur}"
            )

        budget_entry_id = None
        if purpose == "spent":
            if not category_id:
                raise ValueError("Для списания на расход необходимо указать категорию бюджета")

            cat = conn.execute("SELECT id FROM budget_categories WHERE id = ?", (category_id,)).fetchone()
            if not cat:
                raise ValueError("Выбранная категория бюджета не найдена")

            # Создаем расход с from_goal_id и курсами
            cursor = conn.execute(
                """
                INSERT INTO budget_entries
                    (category_id, amount, currency, date, comment, from_goal_id, rate_usd, rate_eur, amount_byn, fx_source, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (category_id, amount, currency, entry_date, comment, goal_id, r_usd, r_eur, byn_val, fx_src, now_iso()),
            )
            last_row = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
            budget_entry_id = last_row["id"] if last_row else cursor.lastrowid

            kind = "withdraw_spent"
        else:
            kind = "withdraw_free"

        # Создаем запись в savings_entries с курсами
        cursor_savings = conn.execute(
            """
            INSERT INTO savings_entries
                (goal_id, amount, currency, date, comment, kind, budget_entry_id, rate_usd, rate_eur, amount_byn, fx_source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (goal_id, amount, currency, entry_date, comment, kind, budget_entry_id, r_usd, r_eur, byn_val, fx_src, now_iso()),
        )
        savings_row = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
        savings_entry_id = savings_row["id"] if savings_row else cursor_savings.lastrowid

    return {
        "savings_entry_id": savings_entry_id,
        "budget_entry_id": budget_entry_id,
        "kind": kind,
        "amount": amount,
        "currency": currency,
    }


def delete_savings_entry(entry_id: int) -> bool:
    """Удаление взноса или снятия (для withdraw_spent удаляется и связанный расход)."""
    with get_db() as conn:
        entry = conn.execute(
            "SELECT id, kind, budget_entry_id FROM savings_entries WHERE id = ?",
            (entry_id,),
        ).fetchone()
        if not entry:
            return False

        if entry["budget_entry_id"]:
            conn.execute(
                "DELETE FROM budget_entries WHERE id = ?",
                (entry["budget_entry_id"],),
            )

        conn.execute("DELETE FROM savings_entries WHERE id = ?", (entry_id,))
    return True


def list_savings_entries_detailed(goal_id: int) -> list[dict]:
    """Список пополнений и снятий по цели с деталями связанной категории."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT e.*, c.name AS category_name
            FROM savings_entries e
            LEFT JOIN budget_entries b ON b.id = e.budget_entry_id
            LEFT JOIN budget_categories c ON c.id = b.category_id
            WHERE e.goal_id = ?
            ORDER BY e.date DESC, e.id DESC
            """,
            (goal_id,),
        ).fetchall()
        return rows_to_dicts(rows)
