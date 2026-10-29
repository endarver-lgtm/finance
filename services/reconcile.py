import json
from datetime import date
from db import get_db, get_setting, now_iso, rows_to_dicts
from services.analytics import budget_fact_own, income_fact, savings_deposits_for_period, savings_withdraw_free_for_period
from services.constants import BASE_CURRENCY
from services.currency import to_byn
from services.dates import parse_date, to_iso
from services.debts import delta_b


def get_last_check() -> dict | None:
    """Возвращает последнюю запись сверки."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM balance_checks ORDER BY date DESC, id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def list_balance_checks() -> list[dict]:
    """Список всех проведенных сверок."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM balance_checks ORDER BY date DESC, id DESC"
        ).fetchall()
        return rows_to_dicts(rows)


def delta_b_strictly_after(after_date_str: str, to_date_str: str) -> float:
    """Изменение баланса долгов для записей с date > after_date_str AND date <= to_date_str."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT amount, currency, kind FROM debts
            WHERE date > ? AND date <= ?
            """,
            (after_date_str, to_date_str),
        ).fetchall()

    delta = 0.0
    for r in rows:
        amt = to_byn(r["amount"], r["currency"])
        kind = r["kind"]
        if kind in ("i_paid", "repay_to_him"):
            delta += amt
        elif kind in ("he_paid", "repay_from_him"):
            delta -= amt

    return round(delta, 2)


def calculate_expected(real_byn: float, check_date: str) -> dict:
    """Расчет ожидаемой суммы и расхождения относительно последней сверки."""
    last = get_last_check()
    savings_in_check = int(get_setting("savings_in_check", "1"))

    if not last:
        return {
            "is_first": True,
            "expected_byn": None,
            "diff_byn": None,
            "savings_in_check": savings_in_check,
            "last_check": None,
        }

    last_date = last["date"]
    to_date = check_date

    with get_db() as conn:
        # Приходы за период date > last_date AND date <= to_date
        inc_rows = conn.execute(
            "SELECT amount, currency FROM income_entries WHERE date > ? AND date <= ?",
            (last_date, to_date),
        ).fetchall()
        income_sum = sum(to_byn(r["amount"], r["currency"]) for r in inc_rows)

        db = delta_b_strictly_after(last_date, to_date)

        if savings_in_check == 1:
            # Все расходы, включая from_goal_id
            exp_rows = conn.execute(
                "SELECT amount, currency FROM budget_entries WHERE date > ? AND date <= ?",
                (last_date, to_date),
            ).fetchall()
            expenses_sum = sum(to_byn(r["amount"], r["currency"]) for r in exp_rows)
            flows = income_sum - expenses_sum - db
        else:
            # Только собственные расходы (from_goal_id IS NULL)
            exp_rows = conn.execute(
                """
                SELECT amount, currency FROM budget_entries
                WHERE date > ? AND date <= ? AND from_goal_id IS NULL
                """,
                (last_date, to_date),
            ).fetchall()
            own_expenses = sum(to_byn(r["amount"], r["currency"]) for r in exp_rows)

            dep_rows = conn.execute(
                """
                SELECT amount, currency FROM savings_entries
                WHERE date > ? AND date <= ? AND kind = 'deposit'
                """,
                (last_date, to_date),
            ).fetchall()
            deposits = sum(to_byn(r["amount"], r["currency"]) for r in dep_rows)

            free_rows = conn.execute(
                """
                SELECT amount, currency FROM savings_entries
                WHERE date > ? AND date <= ? AND kind = 'withdraw_free'
                """,
                (last_date, to_date),
            ).fetchall()
            withdraw_free = sum(to_byn(r["amount"], r["currency"]) for r in free_rows)

            flows = income_sum - own_expenses - deposits + withdraw_free - db

    expected_byn = round(float(last["real_byn"]) + flows, 2)
    diff_byn = round(real_byn - expected_byn, 2)

    return {
        "is_first": False,
        "expected_byn": expected_byn,
        "diff_byn": diff_byn,
        "flows": round(flows, 2),
        "savings_in_check": savings_in_check,
        "last_check": last,
    }


def save_check(
    real_breakdown: dict,
    check_date: str,
    resolution: str = "default",
    comment: str | None = None,
) -> dict:
    """Сохранение сверки с опциональной корректировкой через 'Неучтёнку' или разовый приход."""
    byn_val = float(real_breakdown.get("byn") or 0.0)
    usd_val = float(real_breakdown.get("usd") or 0.0)
    eur_val = float(real_breakdown.get("eur") or 0.0)

    real_byn = round(to_byn(byn_val, "BYN") + to_byn(usd_val, "USD") + to_byn(eur_val, "EUR"), 2)

    calc = calculate_expected(real_byn, check_date)
    is_first = calc["is_first"]
    expected_byn = calc["expected_byn"]
    diff_byn = calc["diff_byn"]
    savings_in_check = calc["savings_in_check"]

    adjust_expense_id = None
    adjust_income_id = None

    with get_db() as conn:
        if not is_first and diff_byn is not None:
            # При diff < 0 и resolution in ('expense', 'default')
            if diff_byn < -0.005 and resolution in ("expense", "default"):
                # Находим категорию 'Неучтёнка'
                cat = conn.execute(
                    "SELECT id FROM budget_categories WHERE name = 'Неучтёнка'"
                ).fetchone()
                if not cat:
                    conn.execute(
                        """
                        INSERT INTO budget_categories (name, planned_amount, currency, period, is_system, track_only, created_at)
                        VALUES ('Неучтёнка', 0, 'BYN', 'month', 1, 1, ?)
                        """,
                        (now_iso(),),
                    )
                    cat = conn.execute("SELECT id FROM budget_categories WHERE name = 'Неучтёнка'").fetchone()

                cat_id = cat["id"]
                cursor = conn.execute(
                    """
                    INSERT INTO budget_entries (category_id, amount, currency, date, comment, created_at)
                    VALUES (?, ?, 'BYN', ?, 'Неучтённый расход (сверка)', ?)
                    """,
                    (cat_id, abs(diff_byn), check_date, now_iso()),
                )
                row = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
                adjust_expense_id = row["id"] if row else cursor.lastrowid

            elif diff_byn > 0.005 and resolution == "income":
                cursor = conn.execute(
                    """
                    INSERT INTO income_entries (source_id, amount, currency, date, comment, created_at)
                    VALUES (NULL, ?, 'BYN', ?, 'Неучтённый приход (сверка)', ?)
                    """,
                    (diff_byn, check_date, now_iso()),
                )
                row = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
                adjust_income_id = row["id"] if row else cursor.lastrowid

        cursor_bc = conn.execute(
            """
            INSERT INTO balance_checks
                (date, real_byn, expected_byn, diff_byn, real_breakdown, savings_in_check,
                 adjust_expense_id, adjust_income_id, comment, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                check_date,
                real_byn,
                expected_byn,
                diff_byn,
                json.dumps(real_breakdown, ensure_ascii=False),
                savings_in_check,
                adjust_expense_id,
                adjust_income_id,
                comment,
                now_iso(),
            ),
        )
        row_bc = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
        check_id = row_bc["id"] if row_bc else cursor_bc.lastrowid

    return {
        "id": check_id,
        "real_byn": real_byn,
        "expected_byn": expected_byn,
        "diff_byn": diff_byn,
        "adjust_expense_id": adjust_expense_id,
        "adjust_income_id": adjust_income_id,
    }
