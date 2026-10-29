from datetime import date

from db import get_db, rows_to_dicts
from services.constants import ONE_TIME_INCOME_LABEL
from services.currency import to_byn
from services.dates import month_label, period_bounds, to_iso
from services.planning import category_planned_for_period
from services.repository import sum_in_range_byn


def income_fact(start: date, end: date) -> float:
    return sum_in_range_byn("income_entries", "date", start, end)


def budget_fact(start: date, end: date) -> float:
    return budget_fact_own(start, end)


def budget_fact_own(start: date, end: date) -> float:
    """Собственные расходы (без трат из копилок)."""
    return sum_in_range_byn(
        "budget_entries", "date", start, end, "from_goal_id IS NULL"
    )


def budget_fact_from_goals(start: date, end: date) -> float:
    """Расходы, оплаченные из копилок."""
    return sum_in_range_byn(
        "budget_entries", "date", start, end, "from_goal_id IS NOT NULL"
    )


def savings_deposits_for_period(start: date, end: date) -> float:
    """Взносы в копилки за период."""
    return sum_in_range_byn(
        "savings_entries", "date", start, end, "kind = 'deposit'"
    )


def savings_withdraw_free_for_period(start: date, end: date) -> float:
    """Возврат из копилок в свободные средства за период."""
    return sum_in_range_byn(
        "savings_entries", "date", start, end, "kind = 'withdraw_free'"
    )


def free_cash_flow(start: date, end: date) -> float:
    """Свободный остаток: Приход - Собственные_расходы - Взносы + Возврат_в_свободные - Delta B."""
    from services.debts import delta_b

    inc = income_fact(start, end)
    own_exp = budget_fact_own(start, end)
    dep = savings_deposits_for_period(start, end)
    w_free = savings_withdraw_free_for_period(start, end)
    db = delta_b(start, end)

    return round(inc - own_exp - dep + w_free - db, 2)


def savings_total() -> float:
    with get_db() as conn:
        rows = conn.execute("SELECT amount, currency, kind FROM savings_entries").fetchall()
    total = 0.0
    for r in rows:
        kind = r["kind"] if "kind" in r.keys() and r["kind"] else "deposit"
        amt = to_byn(r["amount"], r["currency"] if "currency" in r.keys() else "BYN")
        if kind == "deposit":
            total += amt
        elif kind in ("withdraw_spent", "withdraw_free"):
            total -= amt
    return round(max(0.0, total), 2)




def expenses_by_category(start: date, end: date):
    with get_db() as conn:
        cats = rows_to_dicts(
            conn.execute("SELECT id, name FROM budget_categories").fetchall()
        )
    result = []
    for c in cats:
        spent = sum_in_range_byn(
            "budget_entries",
            "date",
            start,
            end,
            "category_id = ?",
            (c["id"],),
        )
        result.append({"id": c["id"], "name": c["name"], "spent": spent})
    result.sort(key=lambda x: (-x["spent"], x["name"]))
    return result


def income_by_months(months):
    labels, plan, fact = [], [], []
    with get_db() as conn:
        sources = conn.execute(
            """
            SELECT id, planned_amount, currency, frequency
            FROM income_sources WHERE active = 1
            """
        ).fetchall()
        received_by_source: dict[int, float] = {}
        for row in conn.execute(
            """
            SELECT source_id, amount, currency FROM income_entries
            WHERE source_id IS NOT NULL
            """
        ).fetchall():
            sid = row["source_id"]
            received_by_source[sid] = received_by_source.get(sid, 0.0) + to_byn(
                row["amount"], row["currency"]
            )
    for m_start, m_end in months:
        labels.append(month_label(m_start))
        p = 0.0
        for s in sources:
            amt = float(s["planned_amount"])
            cur = s["currency"] if "currency" in s.keys() else "BYN"
            planned_byn = to_byn(amt, cur)
            if s["frequency"] == "monthly":
                p += planned_byn
            elif s["frequency"] == "weekly":
                p += to_byn(amt * 4, cur)
            elif s["frequency"] == "one_time":
                received = received_by_source.get(s["id"], 0.0)
                if received < planned_byn - 0.005 and m_start <= date.today() <= m_end:
                    p += planned_byn
        plan.append(round(p, 2))
        fact.append(income_fact(m_start, m_end))
    return labels, plan, fact


def envelope_progress(period: str = "week", ref: date | None = None):
    start, end = period_bounds(period, ref)
    result = []
    with get_db() as conn:
        cats = rows_to_dicts(
            conn.execute(
                "SELECT * FROM budget_categories WHERE track_only = 0 ORDER BY name"
            ).fetchall()
        )
    for c in cats:
        planned_native = category_planned_for_period(c, period)
        cur = c.get("currency", "BYN")
        planned_byn = to_byn(planned_native, cur)
        spent = sum_in_range_byn(
            "budget_entries",
            "date",
            start,
            end,
            "category_id = ? AND from_goal_id IS NULL",
            (c["id"],),
        )
        result.append({
            "id": c["id"],
            "name": c["name"],
            "planned": planned_native,
            "planned_currency": cur,
            "planned_byn": planned_byn,
            "spent": spent,
            "remaining": max(0, planned_byn - spent),
            "pct": min(100, round(spent / planned_byn * 100, 1)) if planned_byn > 0 else 0,
        })
    return result



def upcoming_income(ref: date | None = None):
    ref = ref or date.today()
    start, end = period_bounds("month", ref)
    items = []
    with get_db() as conn:
        sources = rows_to_dicts(
            conn.execute(
                """
                SELECT * FROM income_sources
                WHERE active = 1 AND frequency != 'one_time'
                ORDER BY name
                """
            ).fetchall()
        )
        for s in sources:
            entries = conn.execute(
                """
                SELECT amount, currency FROM income_entries
                WHERE source_id = ? AND date >= ? AND date <= ?
                """,
                (s["id"], to_iso(start), to_iso(end)),
            ).fetchall()
            fact_byn = sum(to_byn(e["amount"], e["currency"]) for e in entries)
            cur = s.get("currency", "BYN")
            planned = float(s["planned_amount"])
            if s["frequency"] == "weekly":
                planned *= 4
            planned_byn = to_byn(planned, cur)
            items.append({
                "id": s["id"],
                "name": s["name"],
                "planned": planned,
                "planned_currency": cur,
                "fact": round(fact_byn, 2),
                "fact_currency": "BYN",
                "status": "received" if fact_byn >= planned_byn else "pending",
            })
    return items


def _date_filter_clause(col: str, date_from, date_to):
    parts, params = [], []
    if date_from:
        parts.append(f"{col} >= ?")
        params.append(to_iso(date_from))
    if date_to:
        parts.append(f"{col} <= ?")
        params.append(to_iso(date_to))
    return (" AND ".join(parts), params) if parts else ("1=1", [])


def history_rows(
    date_from: date | None,
    date_to: date | None,
    type_filter: str,
    category_filter: str,
):
    rows = []

    if type_filter in ("", "income"):
        clause, params = _date_filter_clause("e.date", date_from, date_to)
        with get_db() as conn:
            for r in conn.execute(
                f"""
                SELECT e.id, e.date, e.amount, e.currency, e.comment,
                       COALESCE(s.name, '{ONE_TIME_INCOME_LABEL}') AS label,
                       'income' AS kind
                FROM income_entries e
                LEFT JOIN income_sources s ON s.id = e.source_id
                WHERE {clause}
                ORDER BY e.date DESC
                """,
                params,
            ).fetchall():
                row = dict(r)
                if category_filter and row["label"] != category_filter:
                    continue
                rows.append(row)

    if type_filter in ("", "expense"):
        clause, params = _date_filter_clause("e.date", date_from, date_to)
        with get_db() as conn:
            for r in conn.execute(
                f"""
                SELECT e.id, e.date, e.amount, e.currency, e.comment,
                       c.name AS label, 'expense' AS kind,
                       g.name AS from_goal_name
                FROM budget_entries e
                JOIN budget_categories c ON c.id = e.category_id
                LEFT JOIN savings_goals g ON g.id = e.from_goal_id
                WHERE {clause}
                ORDER BY e.date DESC
                """,
                params,
            ).fetchall():
                row = dict(r)
                if category_filter and row["label"] != category_filter:
                    continue
                rows.append(row)

    if type_filter in ("", "savings", "savings_withdraw"):
        clause, params = _date_filter_clause("e.date", date_from, date_to)
        with get_db() as conn:
            for r in conn.execute(
                f"""
                SELECT e.id, e.date, e.amount, e.currency, e.comment,
                       g.name AS label, e.kind AS entry_kind
                FROM savings_entries e
                JOIN savings_goals g ON g.id = e.goal_id
                WHERE {clause}
                ORDER BY e.date DESC
                """,
                params,
            ).fetchall():
                row = dict(r)
                if category_filter and row["label"] != category_filter:
                    continue
                e_kind = row.get("entry_kind") or "deposit"
                row_kind = "savings" if e_kind == "deposit" else "savings_withdraw"
                if type_filter and type_filter != row_kind:
                    continue
                row["kind"] = row_kind
                row["raw_kind"] = e_kind
                rows.append(row)

    if type_filter in ("", "debt"):
        clause, params = _date_filter_clause("d.date", date_from, date_to)
        with get_db() as conn:
            for r in conn.execute(
                f"""
                SELECT d.id, d.date, d.amount, d.currency, d.comment,
                       d.person AS label, 'debt' AS kind, d.kind AS debt_kind
                FROM debts d
                WHERE {clause}
                ORDER BY d.date DESC
                """,
                params,
            ).fetchall():
                row = dict(r)
                if category_filter and row["label"] != category_filter:
                    continue
                d_kind = row.get("debt_kind")
                row["sign"] = "+" if d_kind in ("i_paid", "repay_to_him") else "−"
                rows.append(row)

    rows.sort(key=lambda x: x["date"], reverse=True)
    return rows

