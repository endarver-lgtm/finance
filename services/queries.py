from datetime import date

from database import get_db
from services.dates import month_label, period_bounds, to_iso


def sum_in_range(table: str, amount_col: str, date_col: str, start: date, end: date, extra: str = "", params=()):
    sql = f"""
        SELECT COALESCE(SUM({amount_col}), 0) AS total
        FROM {table}
        WHERE {date_col} >= %s AND {date_col} <= %s
    """
    if extra:
        sql += f" AND {extra}"
    with get_db() as conn:
        row = conn.execute(sql, (to_iso(start), to_iso(end), *params)).fetchone()
    return float(row["total"])


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


def income_planned_for_period(period: str, ref: date | None = None) -> float:
    start, end = period_bounds(period, ref)
    days = (end - start).days + 1
    total = 0.0
    with get_db() as conn:
        sources = conn.execute(
            "SELECT * FROM income_sources WHERE active = 1"
        ).fetchall()
    for s in sources:
        amt = float(s["planned_amount"])
        freq = s["frequency"]
        if freq == "one_time":
            if s["type"] == "one_time":
                if start <= date.today() <= end:
                    total += amt
            continue
        if freq == "monthly":
            if period == "day":
                total += amt / 30
            elif period == "week":
                total += amt / 4
            elif period == "month":
                total += amt
            elif period == "year":
                total += amt * 12
        elif freq == "weekly":
            if period == "day":
                total += amt / 7
            elif period == "week":
                total += amt
            elif period == "month":
                total += amt * 4
            elif period == "year":
                total += amt * 52
    return round(total, 2)


def budget_planned_for_period(period: str, ref: date | None = None) -> float:
    """Dashboard uses main period; budget page may use week/month only."""
    start, end = period_bounds(period if period in ("week", "month") else "month", ref)
    total = 0.0
    with get_db() as conn:
        cats = conn.execute("SELECT * FROM budget_categories").fetchall()
    for c in cats:
        amt = float(c["planned_amount"])
        cat_period = c["period"]
        if period == "day":
            if cat_period == "week":
                total += amt / 7
            else:
                total += amt / 30
        elif period == "week":
            if cat_period == "week":
                total += amt
            else:
                total += amt / 4
        elif period == "month":
            if cat_period == "month":
                total += amt
            else:
                total += amt * 4
        elif period == "year":
            if cat_period == "month":
                total += amt * 12
            else:
                total += amt * 52
    return round(total, 2)


def category_planned_for_period(cat: dict, period: str) -> float:
    amt = float(cat["planned_amount"])
    cat_period = cat["period"]
    if period == "week":
        return amt if cat_period == "week" else round(amt / 4, 2)
    if period == "month":
        return amt if cat_period == "month" else round(amt * 4, 2)
    return amt


def expenses_by_category(start: date, end: date):
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.name,
                   COALESCE(SUM(e.amount), 0) AS spent
            FROM budget_categories c
            LEFT JOIN budget_entries e
              ON e.category_id = c.id
             AND e.date >= %s AND e.date <= %s
            GROUP BY c.id
            ORDER BY spent DESC, c.name
            """,
            (to_iso(start), to_iso(end)),
        ).fetchall()
    return [dict(r) for r in rows]


def income_by_months(months):
    labels, plan, fact = [], [], []
    with get_db() as conn:
        sources = conn.execute(
            "SELECT * FROM income_sources WHERE active = 1"
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
        cats = conn.execute("SELECT * FROM budget_categories ORDER BY name").fetchall()
    for c in cats:
        c = dict(c)
        planned = category_planned_for_period(c, period)
        spent = sum_in_range(
            "budget_entries", "amount", "date", start, end,
            "category_id = %s", (c["id"],),
        )
        pct = min(100, round(spent / planned * 100, 1)) if planned > 0 else 0
        result.append({
            "id": c["id"],
            "name": c["name"],
            "planned": planned,
            "spent": spent,
            "remaining": max(0, planned - spent),
            "pct": pct,
        })
    return result


def upcoming_income(ref: date | None = None):
    ref = ref or date.today()
    start, end = period_bounds("month", ref)
    items = []
    with get_db() as conn:
        sources = conn.execute(
            """
            SELECT * FROM income_sources
            WHERE active = 1 AND frequency != 'one_time'
            ORDER BY name
            """
        ).fetchall()
        for s in sources:
            s = dict(s)
            fact = conn.execute(
                """
                SELECT COALESCE(SUM(amount), 0) AS total
                FROM income_entries
                WHERE source_id = %s AND date >= %s AND date <= %s
                """,
                (s["id"], to_iso(start), to_iso(end)),
            ).fetchone()["total"]
            planned = float(s["planned_amount"])
            if s["frequency"] == "weekly":
                planned = planned * 4
            status = "received" if float(fact) >= planned else "pending"
            items.append({
                "id": s["id"],
                "name": s["name"],
                "planned": planned,
                "fact": float(fact),
                "status": status,
            })
    return items


def goal_saved(goal_id: int) -> float:
    with get_db() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS t FROM savings_entries WHERE goal_id = %s",
            (goal_id,),
        ).fetchone()
    return float(row["t"])


def history_rows(date_from: date | None, date_to: date | None, type_filter: str, category_filter: str):
    rows = []
    df = to_iso(date_from) if date_from else None
    dt = to_iso(date_to) if date_to else None

    def in_range_clause(col):
        parts, p = [], []
        if df:
            parts.append(f"{col} >= %s")
            p.append(df)
        if dt:
            parts.append(f"{col} <= %s")
            p.append(dt)
        return (" AND ".join(parts), p) if parts else ("1=1", [])

    if type_filter in ("", "income"):
        clause, p = in_range_clause("e.date")
        with get_db() as conn:
            for r in conn.execute(
                f"""
                SELECT e.id, e.date, e.amount, e.comment,
                       COALESCE(s.name, 'Разовый доход') AS label,
                       'income' AS kind
                FROM income_entries e
                LEFT JOIN income_sources s ON s.id = e.source_id
                WHERE {clause}
                ORDER BY e.date DESC
                """,
                p,
            ).fetchall():
                if category_filter and category_filter not in (r["label"], ""):
                    continue
                rows.append(dict(r))

    if type_filter in ("", "expense"):
        clause, p = in_range_clause("e.date")
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
                p,
            ).fetchall():
                if category_filter and r["label"] != category_filter:
                    continue
                rows.append(dict(r))

    if type_filter in ("", "savings"):
        clause, p = in_range_clause("e.date")
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
                p,
            ).fetchall():
                if category_filter and r["label"] != category_filter:
                    continue
                rows.append(dict(r))

    rows.sort(key=lambda x: x["date"], reverse=True)
    return rows
