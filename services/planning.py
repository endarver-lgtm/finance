from datetime import date

from services.currency import to_byn
from services.dates import period_bounds

_FREQ_SCALE = {
    "weekly": {"day": 1 / 7, "week": 1, "month": 4, "year": 52},
    "monthly": {"day": 1 / 30, "week": 1 / 4, "month": 1, "year": 12},
}


def scale_by_frequency(amount: float, frequency: str, view_period: str) -> float:
    if frequency == "one_time":
        return amount
    scales = _FREQ_SCALE.get(frequency, {})
    return amount * scales.get(view_period, 1)


def income_planned_for_period(period: str, ref: date | None = None) -> float:
    from db import get_db

    start, end = period_bounds(period, ref)
    total_byn = 0.0
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
    for s in sources:
        amt = float(s["planned_amount"])
        cur = s["currency"] if "currency" in s.keys() else "BYN"
        planned_byn = to_byn(amt, cur)
        if s["frequency"] == "one_time":
            received = received_by_source.get(s["id"], 0.0)
            if received < planned_byn - 0.005 and start <= date.today() <= end:
                total_byn += planned_byn
            continue
        scaled = scale_by_frequency(amt, s["frequency"], period)
        total_byn += to_byn(scaled, cur)
    return round(total_byn, 2)


def budget_planned_for_period(period: str, ref: date | None = None) -> float:
    from db import get_db

    view = period if period in ("week", "month") else "month"
    total_byn = 0.0
    with get_db() as conn:
        cats = conn.execute(
            "SELECT planned_amount, currency, period FROM budget_categories"
        ).fetchall()
    for c in cats:
        cat = dict(c)
        scaled = category_planned_for_period(cat, view)
        cur = cat.get("currency", "BYN")
        total_byn += to_byn(scaled, cur)
    return round(total_byn, 2)


def category_planned_for_period(cat: dict, view_period: str) -> float:
    amt = float(cat["planned_amount"])
    cat_period = cat["period"]
    if view_period == "week":
        return amt if cat_period == "week" else round(amt / 4, 2)
    if view_period == "month":
        return amt if cat_period == "month" else round(amt * 4, 2)
    return amt


def source_planned_for_period(
    source: dict,
    view_period: str,
    *,
    total_received: float | None = None,
) -> float:
    planned = float(source["planned_amount"])
    freq = source.get("frequency", "monthly")
    if freq == "one_time":
        received = (
            float(source["total_fact"])
            if total_received is None and "total_fact" in source
            else (total_received or 0.0)
        )
        if received >= planned - 0.005:
            return 0.0
        return planned
    if freq == "weekly" and view_period == "month":
        return planned * 4
    if freq == "weekly" and view_period == "year":
        return planned * 52
    return scale_by_frequency(planned, freq, view_period)
