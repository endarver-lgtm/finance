from datetime import date, timedelta
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
                        (person, kind, amount, currency, date, comment, budget_entry_id, category_id, offset_date, source, rate_usd, rate_eur, amount_byn, fx_source, created_at)
                    VALUES (?, 'i_paid', ?, ?, ?, ?, ?, ?, ?, 'split', ?, ?, ?, ?, ?)
                    """,
                    (person, his_share, currency, entry_date, comment, budget_entry_id, category_id, entry_date, r_usd, r_eur, byn_val, fx_src, now_iso()),
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
                        (person, kind, amount, currency, date, comment, budget_entry_id, category_id, offset_date, source, rate_usd, rate_eur, amount_byn, fx_source, created_at)
                    VALUES (?, 'he_paid', ?, ?, ?, ?, ?, ?, ?, 'split', ?, ?, ?, ?, ?)
                    """,
                    (person, my_share, currency, entry_date, comment, budget_entry_id, category_id, entry_date, r_usd, r_eur, byn_val, fx_src, now_iso()),
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
    category_id: int | None = None,
    offset_date: str | None = None,
    expense_id: int | None = None,
    source: str = "manual",
) -> int:
    """Добавление ручной записи долга или возврата с поддержкой зачёта (Этап J)."""
    amount = round(float(amount), 2)
    if amount <= 0:
        raise ValueError("Сумма должна быть больше нуля")

    valid_kinds = ("i_paid", "he_paid", "repay_from_him", "repay_to_him")
    if kind not in valid_kinds:
        raise ValueError(f"Недопустимый тип записи долга: {kind}")

    person = (person or "").strip() or get_setting("default_debt_person", "Кент")
    currency = normalize_currency(currency)
    r_usd, r_eur, byn_val, fx_src = compute_entry_fx(amount, currency)

    cat_id = int(category_id) if category_id not in (None, "", "None") else None
    exp_id = int(expense_id) if expense_id not in (None, "", "None") else None
    off_date = (offset_date or "").strip() or None

    with get_db() as conn:
        # J4: Если задан expense_id, период и категория берутся из расхода (если не заданы)
        if exp_id:
            exp_row = conn.execute("SELECT id, category_id, date FROM budget_entries WHERE id = ?", (exp_id,)).fetchone()
            if exp_row:
                if not cat_id:
                    cat_id = exp_row["category_id"]
                if not off_date:
                    off_date = exp_row["date"]

        if kind in ("i_paid", "he_paid") and not off_date:
            off_date = entry_date

        budget_entry_id = None

        # J2: Для долгов he_paid (я должен ему) с категорией: создать неденежный расход на сумму долга в этой категории
        if kind == "he_paid" and cat_id:
            c_usd, c_eur, c_byn, c_src = compute_entry_fx(amount, currency)
            cursor = conn.execute(
                """
                INSERT INTO budget_entries
                    (category_id, amount, currency, date, comment, rate_usd, rate_eur, amount_byn, fx_source, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (cat_id, amount, currency, off_date or entry_date, comment or f"Долг: {person}", c_usd, c_eur, c_byn, c_src, now_iso()),
            )
            row = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
            budget_entry_id = row["id"] if row else cursor.lastrowid
        elif kind in ("repay_from_him", "repay_to_him"):
            # Погашения не меняют категории
            cat_id = None
            off_date = None
            exp_id = None

        cursor = conn.execute(
            """
            INSERT INTO debts
                (person, kind, amount, currency, date, comment, budget_entry_id, category_id, offset_date, expense_id, source, rate_usd, rate_eur, amount_byn, fx_source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (person, kind, amount, currency, entry_date, comment, budget_entry_id, cat_id, off_date, exp_id, source, r_usd, r_eur, byn_val, fx_src, now_iso()),
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


def update_debt(
    debt_id: int,
    person: str,
    kind: str,
    amount: float,
    currency: str,
    entry_date: str,
    comment: str | None = None,
    category_id: int | None = None,
    offset_date: str | None = None,
    expense_id: int | None = None,
):
    """Обновление записи долга (и связанного расхода, если есть)."""
    amount = round(float(amount), 2)
    if amount <= 0:
        raise ValueError("Сумма должна быть больше нуля")
    currency = normalize_currency(currency)
    r_usd, r_eur, byn_val, fx_src = compute_entry_fx(amount, currency)

    cat_id = int(category_id) if category_id not in (None, "", "None") else None
    exp_id = int(expense_id) if expense_id not in (None, "", "None") else None
    off_date = (offset_date or "").strip() or None

    with get_db() as conn:
        debt = conn.execute("SELECT * FROM debts WHERE id = ?", (debt_id,)).fetchone()
        if not debt:
            raise ValueError("Запись долга не найдена")

        if exp_id:
            exp_row = conn.execute("SELECT id, category_id, date FROM budget_entries WHERE id = ?", (exp_id,)).fetchone()
            if exp_row:
                if not cat_id:
                    cat_id = exp_row["category_id"]
                if not off_date:
                    off_date = exp_row["date"]

        if kind in ("i_paid", "he_paid") and not off_date:
            off_date = entry_date

        if kind in ("repay_from_him", "repay_to_him"):
            cat_id = None
            off_date = None
            exp_id = None

        b_entry_id = debt["budget_entry_id"]

        # J2: Управление неденежным расходом для he_paid
        if kind == "he_paid" and cat_id:
            c_usd, c_eur, c_byn, c_src = compute_entry_fx(amount, currency)
            if b_entry_id:
                conn.execute(
                    """
                    UPDATE budget_entries
                    SET category_id = ?, amount = ?, currency = ?, date = ?, comment = ?,
                        rate_usd = ?, rate_eur = ?, amount_byn = ?, fx_source = ?
                    WHERE id = ?
                    """,
                    (cat_id, amount, currency, off_date or entry_date, comment or f"Долг: {person}", c_usd, c_eur, c_byn, c_src, b_entry_id),
                )
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO budget_entries
                        (category_id, amount, currency, date, comment, rate_usd, rate_eur, amount_byn, fx_source, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (cat_id, amount, currency, off_date or entry_date, comment or f"Долг: {person}", c_usd, c_eur, c_byn, c_src, now_iso()),
                )
                row = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
                b_entry_id = row["id"] if row else cursor.lastrowid
        else:
            # Если раньше был budget_entry_id, а теперь he_paid без категории или другой тип — удаляем расход
            if b_entry_id:
                conn.execute("DELETE FROM budget_entries WHERE id = ?", (b_entry_id,))
                b_entry_id = None

        conn.execute(
            """
            UPDATE debts
            SET person = ?, kind = ?, amount = ?, currency = ?, date = ?, comment = ?,
                budget_entry_id = ?, category_id = ?, offset_date = ?, expense_id = ?,
                rate_usd = ?, rate_eur = ?, amount_byn = ?, fx_source = ?
            WHERE id = ?
            """,
            (person.strip(), kind, amount, currency, entry_date, comment, b_entry_id, cat_id, off_date, exp_id, r_usd, r_eur, byn_val, fx_src, debt_id),
        )


def list_debts(person: str | None = None) -> list[dict]:
    """Список записей долгов с информацией о категории и зачёте."""
    sql = """
        SELECT d.*,
               COALESCE(d.category_id, b.category_id) AS effective_category_id,
               COALESCE(c.name, cd.name) AS category_name,
               exp.comment AS linked_expense_comment,
               exp.amount AS linked_expense_amount
        FROM debts d
        LEFT JOIN budget_entries b ON b.id = d.budget_entry_id
        LEFT JOIN budget_categories c ON c.id = b.category_id
        LEFT JOIN budget_categories cd ON cd.id = d.category_id
        LEFT JOIN budget_entries exp ON exp.id = d.expense_id
    """
    params = ()
    if person:
        sql += " WHERE d.person = ?"
        params = (person.strip(),)
    sql += " ORDER BY d.date DESC, d.id DESC"

    with get_db() as conn:
        return rows_to_dicts(conn.execute(sql, params).fetchall())


def get_debt_offsets(start: date, end: date) -> dict[int, float]:
    """
    Offset(c, период) = Σ amount_byn долгов i_paid (мне должны),
    source='manual', category_id = c, COALESCE(offset_date, date) в периоде [start, end].
    """
    start_str = to_iso(start)
    end_str = to_iso(end)
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT category_id, amount, currency, amount_byn
            FROM debts
            WHERE kind = 'i_paid'
              AND source = 'manual'
              AND category_id IS NOT NULL
              AND COALESCE(offset_date, date) >= ?
              AND COALESCE(offset_date, date) <= ?
            """,
            (start_str, end_str),
        ).fetchall()

    offsets: dict[int, float] = {}
    for r in rows:
        cid = int(r["category_id"])
        amt = float(r["amount_byn"]) if r["amount_byn"] is not None else to_byn(r["amount"], r["currency"])
        offsets[cid] = round(offsets.get(cid, 0.0) + amt, 2)
    return offsets


def total_debt_offset(start: date, end: date) -> float:
    """Σ Offset(c) по всем категориям за период."""
    offsets = get_debt_offsets(start, end)
    return round(sum(offsets.values()), 2)


def find_candidate_expenses(category_id: int | None, target_date: str, debt_amount: float) -> list[dict]:
    """
    J4: Кандидаты для привязки: расходы той же категории за ±7 дней с суммой >= суммы долга.
    """
    from services.dates import parse_date
    dt = parse_date(target_date) or date.today()
    from_date = to_iso(dt - timedelta(days=7))
    to_date = to_iso(dt + timedelta(days=7))

    sql = """
        SELECT b.id, b.date, b.amount, b.currency, b.amount_byn, b.comment, c.name AS category_name
        FROM budget_entries b
        JOIN budget_categories c ON c.id = b.category_id
        WHERE b.date >= ? AND b.date <= ?
          AND b.from_goal_id IS NULL
          AND b.id NOT IN (SELECT adjust_expense_id FROM balance_checks WHERE adjust_expense_id IS NOT NULL)
    """
    params = [from_date, to_date]
    if category_id:
        sql += " AND b.category_id = ?"
        params.append(category_id)

    with get_db() as conn:
        rows = rows_to_dicts(conn.execute(sql, tuple(params)).fetchall())

    # Фильтруем те, где сумма расхода >= суммы долга (с допуском 0.01)
    candidates = []
    for r in rows:
        val = float(r["amount_byn"]) if r["amount_byn"] is not None else to_byn(r["amount"], r["currency"])
        if val >= (debt_amount - 0.01):
            candidates.append(r)

    # Сортируем: сначала ближайшие по сумме, затем по дате
    candidates.sort(key=lambda x: (abs((float(x["amount_byn"] or x["amount"])) - debt_amount), x["date"]), reverse=False)
    return candidates


def get_uncategorized_debts() -> list[dict]:
    """
    J5: «Неразнесённое»: долги i_paid / he_paid без категории.
    """
    sql = """
        SELECT d.*
        FROM debts d
        WHERE d.kind IN ('i_paid', 'he_paid')
          AND d.category_id IS NULL
          AND d.budget_entry_id IS NULL
        ORDER BY d.date DESC, d.id DESC
    """
    with get_db() as conn:
        return rows_to_dicts(conn.execute(sql).fetchall())


def get_friends_money_card() -> dict:
    """
    J7: Карточка «Деньги у друзей»: остатки по людям и давность самого старого долга.
    """
    from datetime import date, timedelta
    from services.dates import parse_date
    persons = list_debt_persons()
    friends = []
    total_positive = 0.0
    today = date.today()

    with get_db() as conn:
        for p in persons:
            bal = debt_balance(p)
            if bal > 0.005:
                # Найти самую старую дату незакрытого долга i_paid
                oldest_row = conn.execute(
                    "SELECT MIN(date) AS min_d FROM debts WHERE person = ? AND kind = 'i_paid'",
                    (p,),
                ).fetchone()
                min_d = oldest_row["min_d"] if oldest_row else None
                days_old = 0
                if min_d:
                    dt = parse_date(min_d)
                    if dt:
                        days_old = max(0, (today - dt).days)
                friends.append({
                    "person": p,
                    "balance": bal,
                    "oldest_date": min_d,
                    "days_old": days_old,
                })
                total_positive += bal

    friends.sort(key=lambda x: -x["balance"])
    oldest_days = max([f["days_old"] for f in friends], default=0)
    return {
        "friends": friends,
        "total_byn": round(total_positive, 2),
        "oldest_days": oldest_days,
        "count": len(friends),
    }


def suggest_matches_for_debts() -> list[dict]:
    """
    J5: Подсказки для экрана «Несвязанные долги»:
    долг ≈ 50% расхода (±1 BYN) или не больше расхода за ±7 дней.
    """
    from services.dates import parse_date
    unlinked = get_uncategorized_debts()
    results = []

    with get_db() as conn:
        for d in unlinked:
            d_amt = float(d["amount_byn"]) if d["amount_byn"] is not None else to_byn(d["amount"], d["currency"])
            d_date = parse_date(d["date"])
            if not d_date:
                continue
            from_d = to_iso(d_date - timedelta(days=7))
            to_d = to_iso(d_date + timedelta(days=7))

            exp_rows = rows_to_dicts(
                conn.execute(
                    """
                    SELECT b.*, c.name AS category_name
                    FROM budget_entries b
                    JOIN budget_categories c ON c.id = b.category_id
                    WHERE b.date >= ? AND b.date <= ?
                      AND b.from_goal_id IS NULL
                      AND b.id NOT IN (SELECT adjust_expense_id FROM balance_checks WHERE adjust_expense_id IS NOT NULL)
                    ORDER BY b.date DESC
                    """,
                    (from_d, to_d),
                ).fetchall()
            )

            suggestions = []
            for e in exp_rows:
                e_amt = float(e["amount_byn"]) if e["amount_byn"] is not None else to_byn(e["amount"], e["currency"])
                # Проверка 50% ± 1 BYN
                is_half = abs((e_amt / 2.0) - d_amt) <= 1.05
                is_candidate = is_half or (e_amt >= (d_amt - 0.01))
                if is_candidate:
                    suggestions.append({
                        "expense_id": e["id"],
                        "category_id": e["category_id"],
                        "category_name": e["category_name"],
                        "date": e["date"],
                        "amount": e_amt,
                        "comment": e["comment"] or "",
                        "is_half": is_half,
                    })

            # Сортируем: сначала те, что 50%, потом остальные
            suggestions.sort(key=lambda s: (not s["is_half"], abs(s["amount"] - 2 * d_amt)))
            results.append({
                "debt": d,
                "suggestions": suggestions,
            })

    return results
