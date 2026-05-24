from datetime import date

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
    total = 0.0
    with get_db() as conn:
        sources = conn.execute(
            "SELECT planned_amount, frequency, type FROM income_sources WHERE active = 1"
        ).fetchall()
    for s in sources:
        if s["frequency"] == "one_time":
            if s["type"] == "one_time" and start <= date.today() <= end:
                total += float(s["planned_amount"])
            continue
        total += scale_by_frequency(
            float(s["planned_amount"]), s["frequency"], period
        )
    return round(total, 2)


def budget_planned_for_period(period: str, ref: date | None = None) -> float:
    from db import get_db

    view = period if period in ("week", "month") else "month"
    total = 0.0
    with get_db() as conn:
        cats = conn.execute(
            "SELECT planned_amount, period FROM budget_categories"
        ).fetchall()
    for c in cats:
        total += category_planned_for_period(dict(c), view)
    return round(total, 2)


def category_planned_for_period(cat: dict, view_period: str) -> float:
    amt = float(cat["planned_amount"])
    cat_period = cat["period"]
    if view_period == "week":
        return amt if cat_period == "week" else round(amt / 4, 2)
    if view_period == "month":
        return amt if cat_period == "month" else round(amt * 4, 2)
    return amt


def source_planned_for_period(source: dict, view_period: str) -> float:
    planned = float(source["planned_amount"])
    if source["frequency"] == "weekly" and view_period == "month":
        return planned * 4
    if source["frequency"] == "weekly" and view_period == "year":
        return planned * 52
    return scale_by_frequency(planned, source["frequency"], view_period)
