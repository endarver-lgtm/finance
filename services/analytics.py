from datetime import date

from db import get_db, rows_to_dicts
from services.constants import ONE_TIME_INCOME_LABEL
from services.dates import month_label, period_bounds, to_iso
from services.planning import category_planned_for_period
from services.repository import sum_in_range


def income_fact(start: date, end: date) -> float:
    return sum_in_range("income_entries", "amount", "date", start, end)


def budget_fact(start: date, end: date) -> float:
    return sum_in_range("budget_entries", "amount", "date", start, end)


def savings_total() -> float:
    with get_db() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM savings_entries"
        ).fetchone()
    return float(row["total"])


def expenses_by_category(start: date, end: date):
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.name, COALESCE(SUM(e.amount), 0) AS spent
            FROM budget_categories c
            LEFT JOIN budget_entries e
              ON e.category_id = c.id
             AND e.date >= ? AND e.date <= ?
            GROUP BY c.id
            ORDER BY spent DESC, c.name
            """,
            (to_iso(start), to_iso(end)),
        ).fetchall()
    return rows_to_dicts(rows)


def income_by_months(months):
    labels, plan, fact = [], [], []
    with get_db() as conn:
        sources = conn.execute(
            "SELECT planned_amount, frequency FROM income_sources WHERE active = 1"
        ).fetchall()
    for m_start, m_end in months:
        labels.append(month_label(m_start))
        p = 0.0
        for s in sources:
            amt = float(s["planned_amount"])
            if s["frequency"] == "monthly":
                p += amt
            elif s["frequency"] == "weekly":
                p += amt * 4
            elif s["frequency"] == "one_time" and m_start <= date.today() <= m_end:
                p += amt
        plan.append(round(p, 2))
        fact.append(income_fact(m_start, m_end))
    return labels, plan, fact


def envelope_progress(period: str = "week", ref: date | None = None):
    start, end = period_bounds(period, ref)
    result = []
    with get_db() as conn:
        cats = rows_to_dicts(
            conn.execute(
                "SELECT * FROM budget_categories ORDER BY name"
            ).fetchall()
        )
    for c in cats:
        planned = category_planned_for_period(c, period)
        spent = sum_in_range(
            "budget_entries",
            "amount",
            "date",
            start,
            end,
            "category_id = ?",
            (c["id"],),
        )
        result.append({
            "id": c["id"],
            "name": c["name"],
            "planned": planned,
            "spent": spent,
            "remaining": max(0, planned - spent),
            "pct": min(100, round(spent / planned * 100, 1)) if planned > 0 else 0,
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
            row = conn.execute(
                """
                SELECT COALESCE(SUM(amount), 0) AS total
                FROM income_entries
                WHERE source_id = ? AND date >= ? AND date <= ?
                """,
                (s["id"], to_iso(start), to_iso(end)),
            ).fetchone()
            fact = float(row["total"])
            planned = float(s["planned_amount"])
            if s["frequency"] == "weekly":
                planned *= 4
            items.append({
                "id": s["id"],
                "name": s["name"],
                "planned": planned,
                "fact": fact,
                "status": "received" if fact >= planned else "pending",
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
                SELECT e.id, e.date, e.amount, e.comment,
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
                SELECT e.id, e.date, e.amount, e.comment,
                       c.name AS label, 'expense' AS kind
                FROM budget_entries e
                JOIN budget_categories c ON c.id = e.category_id
                WHERE {clause}
                ORDER BY e.date DESC
                """,
                params,
            ).fetchall():
                row = dict(r)
                if category_filter and row["label"] != category_filter:
                    continue
                rows.append(row)

    if type_filter in ("", "savings"):
        clause, params = _date_filter_clause("e.date", date_from, date_to)
        with get_db() as conn:
            for r in conn.execute(
                f"""
                SELECT e.id, e.date, e.amount, e.comment,
                       g.name AS label, 'savings' AS kind
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
                rows.append(row)

    rows.sort(key=lambda x: x["date"], reverse=True)
    return rows
