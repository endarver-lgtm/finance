from datetime import date
from db import get_db, get_setting, now_iso, rows_to_dicts
from services.constants import BASE_CURRENCY
from services.currency import compute_entry_fx, convert, normalize_currency, to_byn
from services.dates import to_iso


def list_debt_persons() -> list[str]:
    """Список всех людей, с которыми были долги, плюс дефолтный человек."""
    default_person = get_setting("default_debt_person", "Кент").strip()
    persons = set()
    if default_person:
        persons.add(default_person)
    with get_db() as conn:
        rows = conn.execute("SELECT DISTINCT person FROM debts ORDER BY person").fetchall()
        for r in rows:
            if r["person"] and r["person"].strip():
                persons.add(r["person"].strip())
    return sorted(persons)


def debt_balance(person: str | None = None, target_currency: str = BASE_CURRENCY) -> float:
    """Баланс долга (положительный = человек должен мне, отрицательный = я должен ему)."""
    target_currency = normalize_currency(target_currency)
    sql = "SELECT amount, currency, kind FROM debts"
    params = ()
    if person:
        sql += " WHERE person = ?"
        params = (person.strip(),)

    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()

    b = 0.0
    for r in rows:
        amt = convert(r["amount"], r["currency"], target_currency)
        kind = r["kind"]
        if kind in ("i_paid", "repay_to_him"):
            b += amt
        elif kind in ("he_paid", "repay_from_him"):
            b -= amt

    return round(b, 2)


def balance_total(target_currency: str = BASE_CURRENCY) -> float:
    """Общий баланс по всем людям."""
    return debt_balance(person=None, target_currency=target_currency)


def delta_b(date_from: date, date_to: date) -> float:
    """Изменение баланса долгов за период в BYN (A1)."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT amount, currency, kind, amount_byn FROM debts
            WHERE date >= ? AND date <= ?
            """,
            (to_iso(date_from), to_iso(date_to)),
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


def add_split(
    total_amount: float,
    currency: str,
    entry_date: str,
    paid_by: str,
    person: str,
    my_share: float,
    category_id: int | None = None,
    comment: str | None = None,
) -> dict:
    """Разделение расхода с человеком."""
    total_amount = round(float(total_amount), 2)
    my_share = round(float(my_share), 2)
    his_share = round(total_amount - my_share, 2)

    if total_amount <= 0:
        raise ValueError("Общая сумма должна быть больше нуля")
    if my_share < 0 or my_share > total_amount + 0.005:
        raise ValueError("Моя доля должна быть в пределах от 0 до общей суммы")
    if paid_by not in ("me", "him"):
        raise ValueError("Некорректное значение поля 'Кто платил'")

    person = (person or "").strip() or get_setting("default_debt_person", "Кент")
    currency = normalize_currency(currency)

    with get_db() as conn:
        budget_entry_id = None

        if paid_by == "me":
            if my_share > 0:
                if not category_id:
                    raise ValueError("Укажите категорию расхода для вашей доли")
                r_usd, r_eur, byn_val, fx_src = compute_entry_fx(my_share, currency)
                cursor = conn.execute(
                    """
                    INSERT INTO budget_entries
                        (category_id, amount, currency, date, comment, rate_usd, rate_eur, amount_byn, fx_source, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (category_id, my_share, currency, entry_date, comment, r_usd, r_eur, byn_val, fx_src, now_iso()),
                )
                row = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
                budget_entry_id = row["id"] if row else cursor.lastrowid

            if his_share > 0:
                r_usd, r_eur, byn_val, fx_src = compute_entry_fx(his_share, currency)
                conn.execute(
                    """
                    INSERT INTO debts
                        (person, kind, amount, currency, date, comment, budget_entry_id, rate_usd, rate_eur, amount_byn, fx_source, created_at)
                    VALUES (?, 'i_paid', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (person, his_share, currency, entry_date, comment, budget_entry_id, r_usd, r_eur, byn_val, fx_src, now_iso()),
                )
        else:  # paid_by == 'him'
            if my_share > 0:
                if not category_id:
                    raise ValueError("Укажите категорию расхода для вашей доли")
                r_usd, r_eur, byn_val, fx_src = compute_entry_fx(my_share, currency)
                cursor = conn.execute(
                    """
                    INSERT INTO budget_entries
                        (category_id, amount, currency, date, comment, rate_usd, rate_eur, amount_byn, fx_source, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (category_id, my_share, currency, entry_date, comment, r_usd, r_eur, byn_val, fx_src, now_iso()),
                )
                row = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
                budget_entry_id = row["id"] if row else cursor.lastrowid

                conn.execute(
                    """
                    INSERT INTO debts
                        (person, kind, amount, currency, date, comment, budget_entry_id, rate_usd, rate_eur, amount_byn, fx_source, created_at)
                    VALUES (?, 'he_paid', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (person, my_share, currency, entry_date, comment, budget_entry_id, r_usd, r_eur, byn_val, fx_src, now_iso()),
                )

    return {
        "budget_entry_id": budget_entry_id,
        "my_share": my_share,
        "his_share": his_share,
        "person": person,
    }


def add_debt_entry(
    person: str,
    kind: str,
    amount: float,
    currency: str,
    entry_date: str,
    comment: str | None = None,
) -> int:
    """Добавление ручной записи долга или возврата."""
    amount = round(float(amount), 2)
    if amount <= 0:
        raise ValueError("Сумма должна быть больше нуля")

    valid_kinds = ("i_paid", "he_paid", "repay_from_him", "repay_to_him")
    if kind not in valid_kinds:
        raise ValueError(f"Недопустимый тип записи долга: {kind}")

    person = (person or "").strip() or get_setting("default_debt_person", "Кент")
    currency = normalize_currency(currency)
    r_usd, r_eur, byn_val, fx_src = compute_entry_fx(amount, currency)

    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO debts
                (person, kind, amount, currency, date, comment, budget_entry_id, rate_usd, rate_eur, amount_byn, fx_source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?)
            """,
            (person, kind, amount, currency, entry_date, comment, r_usd, r_eur, byn_val, fx_src, now_iso()),
        )
        row = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
        return row["id"] if row else cursor.lastrowid


def delete_debt(debt_id: int) -> bool:
    """Удаление записи долга (вместе со связанным расходом, если есть)."""
    with get_db() as conn:
        debt = conn.execute("SELECT * FROM debts WHERE id = ?", (debt_id,)).fetchone()
        if not debt:
            return False

        if debt["budget_entry_id"]:
            conn.execute("DELETE FROM budget_entries WHERE id = ?", (debt["budget_entry_id"],))

        conn.execute("DELETE FROM debts WHERE id = ?", (debt_id,))
    return True


def update_debt(debt_id: int, person: str, kind: str, amount: float, currency: str, entry_date: str, comment: str):
    """Обновление записи долга (и связанного расхода, если есть)."""
    amount = round(float(amount), 2)
    if amount <= 0:
        raise ValueError("Сумма должна быть больше нуля")
    currency = normalize_currency(currency)
    r_usd, r_eur, byn_val, fx_src = compute_entry_fx(amount, currency)

    with get_db() as conn:
        debt = conn.execute("SELECT budget_entry_id FROM debts WHERE id = ?", (debt_id,)).fetchone()
        if not debt:
            raise ValueError("Запись долга не найдена")
        conn.execute(
            """
            UPDATE debts
            SET person = ?, kind = ?, amount = ?, currency = ?, date = ?, comment = ?,
                rate_usd = ?, rate_eur = ?, amount_byn = ?, fx_source = ?
            WHERE id = ?
            """,
            (person.strip(), kind, amount, currency, entry_date, comment, r_usd, r_eur, byn_val, fx_src, debt_id),
        )
        if debt["budget_entry_id"]:
            conn.execute(
                """
                UPDATE budget_entries
                SET amount = ?, currency = ?, date = ?, comment = ?,
                    rate_usd = ?, rate_eur = ?, amount_byn = ?, fx_source = ?
                WHERE id = ?
                """,
                (amount, currency, entry_date, comment, r_usd, r_eur, byn_val, fx_src, debt["budget_entry_id"]),
            )


def list_debts(person: str | None = None) -> list[dict]:
    """Список записей долгов."""
    sql = """
        SELECT d.*, b.category_id, c.name AS category_name
        FROM debts d
        LEFT JOIN budget_entries b ON b.id = d.budget_entry_id
        LEFT JOIN budget_categories c ON c.id = b.category_id
    """
    params = ()
    if person:
        sql += " WHERE d.person = ?"
        params = (person.strip(),)
    sql += " ORDER BY d.date DESC, d.id DESC"

    with get_db() as conn:
        return rows_to_dicts(conn.execute(sql, params).fetchall())
