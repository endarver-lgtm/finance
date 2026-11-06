import json
from datetime import date
from db import get_db, get_setting, now_iso, rows_to_dicts
from services.constants import BASE_CURRENCY
from services.currency import compute_entry_fx, eur_rate, to_byn, usd_rate
from services.dates import parse_date, to_iso


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
            SELECT amount, currency, kind, amount_byn FROM debts
            WHERE date > ? AND date <= ?
            """,
            (after_date_str, to_date_str),
        ).fetchall()

    delta = 0.0
    for r in rows:
        amt = (
            float(r["amount_byn"])
            if ("amount_byn" in r.keys() and r["amount_byn"] is not None)
            else to_byn(r["amount"], r["currency"])
        )
        kind = r["kind"]
        if kind in ("i_paid", "repay_to_him"):
            delta += amt
        elif kind in ("he_paid", "repay_from_him"):
            delta -= amt

    return round(delta, 2)


def calculate_expected(real_byn: float, check_date: str) -> dict:
    """Расчет ожидаемой суммы и расхождения относительно последней сверки (A1/A2)."""
    last = get_last_check()
    savings_in_check = int(get_setting("savings_in_check", "1"))

    if not last:
        return {
            "is_first": True,
            "expected_byn": None,
            "diff_byn": None,
            "diff_clean": None,
            "fx_effect": 0.0,
            "savings_in_check": savings_in_check,
            "last_check": None,
        }

    last_date = last["date"]
    to_date = check_date
    cur_r_usd = usd_rate()
    cur_r_eur = eur_rate()

    # Расчет курсовой разницы между сверками (A2)
    fx_effect = 0.0
    try:
        last_bd = json.loads(last["real_breakdown"]) if last.get("real_breakdown") else {}
    except Exception:
        last_bd = {}
    last_usd = float(last_bd.get("usd") or 0.0)
    last_eur = float(last_bd.get("eur") or 0.0)
    last_r_usd = float(last.get("rate_usd") or cur_r_usd)
    last_r_eur = float(last.get("rate_eur") or cur_r_eur)
    fx_effect = round(
        last_usd * (cur_r_usd - last_r_usd) + last_eur * (cur_r_eur - last_r_eur),
        2,
    )

    with get_db() as conn:
        # Приходы за период date > last_date AND date <= to_date (по amount_byn)
        inc_rows = conn.execute(
            "SELECT amount, currency, amount_byn FROM income_entries WHERE date > ? AND date <= ?",
            (last_date, to_date),
        ).fetchall()
        income_sum = sum(
            float(r["amount_byn"]) if r["amount_byn"] is not None else to_byn(r["amount"], r["currency"])
            for r in inc_rows
        )

        db = delta_b_strictly_after(last_date, to_date)

        if savings_in_check == 1:
            # Все расходы, включая from_goal_id
            exp_rows = conn.execute(
                "SELECT amount, currency, amount_byn FROM budget_entries WHERE date > ? AND date <= ?",
                (last_date, to_date),
            ).fetchall()
            expenses_sum = sum(
                float(r["amount_byn"]) if r["amount_byn"] is not None else to_byn(r["amount"], r["currency"])
                for r in exp_rows
            )
            flows = income_sum - expenses_sum - db
        else:
            # Только собственные расходы (from_goal_id IS NULL)
            exp_rows = conn.execute(
                """
                SELECT amount, currency, amount_byn FROM budget_entries
                WHERE date > ? AND date <= ? AND from_goal_id IS NULL
                """,
                (last_date, to_date),
            ).fetchall()
            own_expenses = sum(
                float(r["amount_byn"]) if r["amount_byn"] is not None else to_byn(r["amount"], r["currency"])
                for r in exp_rows
            )

            dep_rows = conn.execute(
                """
                SELECT amount, currency, amount_byn FROM savings_entries
                WHERE date > ? AND date <= ? AND kind = 'deposit'
                """,
                (last_date, to_date),
            ).fetchall()
            deposits = sum(
                float(r["amount_byn"]) if r["amount_byn"] is not None else to_byn(r["amount"], r["currency"])
                for r in dep_rows
            )

            free_rows = conn.execute(
                """
                SELECT amount, currency, amount_byn FROM savings_entries
                WHERE date > ? AND date <= ? AND kind = 'withdraw_free'
                """,
                (last_date, to_date),
            ).fetchall()
            withdraw_free = sum(
                float(r["amount_byn"]) if r["amount_byn"] is not None else to_byn(r["amount"], r["currency"])
                for r in free_rows
            )

            flows = income_sum - own_expenses - deposits + withdraw_free - db

    expected_byn = round(float(last["real_byn"]) + flows, 2)
    diff_byn = round(real_byn - expected_byn, 2)
    
    # diff_clean = diff - fx_effect (A2)
    diff_clean = round(diff_byn - fx_effect, 2)
    if abs(diff_clean) <= 0.005:
        diff_clean = 0.0

    return {
        "is_first": False,
        "expected_byn": expected_byn,
        "diff_byn": diff_byn,
        "diff_clean": diff_clean,
        "fx_effect": fx_effect,
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
    """Сохранение сверки с учетом курсовой разницы и корректировкой через 'Неучтёнку' (A2)."""
    byn_val = float(real_breakdown.get("byn") or 0.0)
    usd_val = float(real_breakdown.get("usd") or 0.0)
    eur_val = float(real_breakdown.get("eur") or 0.0)

    cur_r_usd = usd_rate()
    cur_r_eur = eur_rate()

    real_byn = round(byn_val + usd_val * cur_r_usd + eur_val * cur_r_eur, 2)

    calc = calculate_expected(real_byn, check_date)
    is_first = calc["is_first"]
    expected_byn = calc["expected_byn"]
    diff_byn = calc["diff_byn"]
    diff_clean = calc["diff_clean"]
    fx_effect = calc["fx_effect"]
    savings_in_check = calc["savings_in_check"]

    adjust_expense_id = None
    adjust_income_id = None

    with get_db() as conn:
        if not is_first and diff_clean is not None and abs(diff_clean) > 0.005:
            # Корректировка создается ТОЛЬКО на diff_clean (A2)
            if diff_clean < -0.005 and resolution in ("expense", "default"):
                # Находим или создаем системную категорию 'Неучтёнка'
                cat = conn.execute(
                    "SELECT id FROM budget_categories WHERE name = 'Неучтёнка'"
                ).fetchone()
                if not cat:
                    conn.execute(
                        """
                        INSERT INTO budget_categories (name, planned_amount, currency, period, is_system, track_only, is_fixed, created_at)
                        VALUES ('Неучтёнка', 0, 'BYN', 'month', 1, 1, 0, ?)
                        """,
                        (now_iso(),),
                    )
                    cat = conn.execute("SELECT id FROM budget_categories WHERE name = 'Неучтёнка'").fetchone()

                cat_id = cat["id"]
                adj_amt = abs(diff_clean)
                cursor = conn.execute(
                    """
                    INSERT INTO budget_entries (category_id, amount, currency, date, comment, rate_usd, rate_eur, amount_byn, fx_source, created_at)
                    VALUES (?, ?, 'BYN', ?, 'Неучтённый расход (сверка)', ?, ?, ?, 'entry', ?)
                    """,
                    (cat_id, adj_amt, check_date, cur_r_usd, cur_r_eur, adj_amt, now_iso()),
                )
                row = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
                adjust_expense_id = row["id"] if row else cursor.lastrowid

            elif diff_clean > 0.005 and resolution == "income":
                adj_amt = diff_clean
                cursor = conn.execute(
                    """
                    INSERT INTO income_entries (source_id, amount, currency, date, comment, rate_usd, rate_eur, amount_byn, fx_source, created_at)
                    VALUES (NULL, ?, 'BYN', ?, 'Неучтённый приход (сверка)', ?, ?, ?, 'entry', ?)
                    """,
                    (adj_amt, check_date, cur_r_usd, cur_r_eur, adj_amt, now_iso()),
                )
                row = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
                adjust_income_id = row["id"] if row else cursor.lastrowid

        cursor_bc = conn.execute(
            """
            INSERT INTO balance_checks
                (date, real_byn, expected_byn, diff_byn, real_breakdown, savings_in_check,
                 adjust_expense_id, adjust_income_id, rate_usd, rate_eur, fx_effect_byn, comment, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                cur_r_usd,
                cur_r_eur,
                fx_effect,
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
        "diff_clean": diff_clean,
        "fx_effect": fx_effect,
        "adjust_expense_id": adjust_expense_id,
        "adjust_income_id": adjust_income_id,
    }
