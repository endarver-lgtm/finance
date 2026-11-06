import json
from datetime import date, timedelta
from typing import Optional

from db import get_db
from services.currency import to_byn
from services.dates import parse_date, period_bounds


def scale_plan(amount: float, plan_period: str, range_from: date, range_to: date) -> float:
    """
    Масштабирование планов по дням без дробления недель и месяцев (D1).
    - Если единица плана совпадает с диапазоном: без пересчета.
    - Иначе через ставку в день: недельный -> amount / 7; месячный -> amount * 12 / 365.
    - Год: недельный * (365 / 7); месячный * 12.
    """
    amt = float(amount or 0)
    if amt <= 0:
        return 0.0

    days = (range_to - range_from).days + 1
    if days <= 0:
        return 0.0

    plan_period = (plan_period or "month").lower().strip()

    is_same_month = (range_from.year == range_to.year and range_from.month == range_to.month)
    is_calendar_month = (
        is_same_month
        and range_from.day == 1
        and (range_to + timedelta(days=1)).month != range_to.month
    )
    is_calendar_year = (
        range_from.month == 1
        and range_from.day == 1
        and range_to.month == 12
        and range_to.day == 31
        and range_from.year == range_to.year
    )

    if plan_period in ("week", "weekly"):
        if days == 7:
            return round(amt, 2)
        if is_calendar_year:
            return round(amt * 365.0 / 7.0, 2)
        return round((amt / 7.0) * days, 2)

    elif plan_period in ("month", "monthly"):
        if is_calendar_month:
            return round(amt, 2)
        if is_calendar_year:
            return round(amt * 12.0, 2)
        return round((amt * 12.0 / 365.0) * days, 2)

    elif plan_period in ("year", "yearly"):
        if is_calendar_year:
            return round(amt, 2)
        return round((amt / 365.0) * days, 2)

    return round(amt, 2)


def income_planned_for_period(period: str, ref: Optional[date] = None) -> float:
    """Плановый приход за период с учетом ожидаемых дат разовых доходов (D1, D2, D3)."""
    start, end = period_bounds(period, ref)
    return income_planned_in_range(start, end)


def income_planned_in_range(start: date, end: date) -> float:
    """Плановый приход за точный диапазон дат [start, end]."""
    total_byn = 0.0
    with get_db() as conn:
        sources = conn.execute(
            """
            SELECT id, type, planned_amount, currency, frequency, expected_date, pay_days, created_at
            FROM income_sources WHERE active = 1
            """
        ).fetchall()

    for s in sources:
        amt = float(s["planned_amount"] or 0)
        cur = s["currency"] if "currency" in s.keys() else "BYN"
        stype = s["type"]
        freq = s["frequency"]

        # Разовые доходы (D2):
        # План учитывается в периоде, содержащем expected_date, и не обнуляется после получения
        if stype == "one_time" or freq == "one_time":
            exp_date_str = s["expected_date"] or (s["created_at"][:10] if s["created_at"] else None)
            exp_d = parse_date(exp_date_str)
            if exp_d and start <= exp_d <= end:
                total_byn += to_byn(amt, cur)
            continue

        # Регулярные доходы с датами выплат pay_days (D3):
        # Если заданы pay_days (например [5, 20]), planned_amount — сумма одной выплаты
        pay_days_raw = s.get("pay_days") if "pay_days" in s.keys() else None
        pay_days = None
        if pay_days_raw:
            try:
                pay_days = json.loads(pay_days_raw)
            except Exception:
                pay_days = None

        if pay_days and isinstance(pay_days, list) and len(pay_days) > 0:
            # Считаем количество выплат, попадающих в диапазон [start, end]
            payouts_count = 0
            curr = start
            while curr <= end:
                if curr.day in pay_days:
                    payouts_count += 1
                curr += timedelta(days=1)
            total_byn += to_byn(amt * payouts_count, cur)
            continue

        # Обычные регулярные доходы по дням scale_plan
        scaled = scale_plan(amt, freq, start, end)
        total_byn += to_byn(scaled, cur)

    return round(total_byn, 2)


def budget_planned_for_period(period: str, ref: Optional[date] = None) -> float:
    """Плановые расходы по всем категориям за период (D1)."""
    start, end = period_bounds(period, ref)
    return budget_planned_in_range(start, end)


def budget_planned_in_range(start: date, end: date) -> float:
    """Плановые расходы за диапазон [start, end]."""
    total_byn = 0.0
    with get_db() as conn:
        cats = conn.execute(
            """
            SELECT planned_amount, currency, period, track_only
            FROM budget_categories
            WHERE track_only = 0
            """
        ).fetchall()

    for c in cats:
        amt = float(c["planned_amount"] or 0)
        cur = c["currency"] if "currency" in c.keys() else "BYN"
        cat_period = c["period"]
        scaled = scale_plan(amt, cat_period, start, end)
        total_byn += to_byn(scaled, cur)

    return round(total_byn, 2)


def category_planned_for_period(cat: dict, view_period: str, ref: Optional[date] = None) -> float:
    """Плановый расход по конкретной категории для выбранного вида (week/month/year)."""
    start, end = period_bounds(view_period, ref)
    amt = float(cat.get("planned_amount") or 0)
    cat_period = cat.get("period", "month")
    return scale_plan(amt, cat_period, start, end)


def source_planned_for_period(
    source: dict,
    view_period: str,
    *,
    ref: Optional[date] = None,
    total_received: Optional[float] = None,
) -> float:
    """Плановый приход по источнику для периода (D1, D2). Не обнуляется при факте >= план!"""
    start, end = period_bounds(view_period, ref)
    planned = float(source.get("planned_amount") or 0)
    stype = source.get("type", "regular")
    freq = source.get("frequency", "monthly")

    if stype == "one_time" or freq == "one_time":
        exp_date_str = source.get("expected_date") or (source.get("created_at", "")[:10] if source.get("created_at") else None)
        exp_d = parse_date(exp_date_str)
        if exp_d and start <= exp_d <= end:
            return planned
        return 0.0

    return scale_plan(planned, freq, start, end)
