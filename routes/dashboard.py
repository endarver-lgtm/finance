from datetime import date

from flask import Blueprint, render_template, request

from services.dates import last_n_months, period_bounds
from services.queries import (
    budget_fact,
    budget_planned_for_period,
    envelope_progress,
    expenses_by_category,
    income_by_months,
    income_fact,
    income_planned_for_period,
    savings_total,
    upcoming_income,
)

bp = Blueprint("dashboard", __name__, url_prefix="/")

PERIODS = {"day": "День", "week": "Неделя", "month": "Месяц", "year": "Год"}


@bp.route("/")
def index():
    period = request.args.get("period", "month")
    if period not in PERIODS:
        period = "month"
    ref = date.today()
    start, end = period_bounds(period, ref)

    income_plan = income_planned_for_period(period, ref)
    income_actual = income_fact(start, end)
    expense_plan = budget_planned_for_period(period, ref)
    expense_actual = budget_fact(start, end)
    free = income_actual - expense_actual
    saved = savings_total()

    chart_start, chart_end = period_bounds("month", ref)
    expense_chart = expenses_by_category(chart_start, chart_end)
    months = last_n_months(6, ref)
    income_labels, income_plan_series, income_fact_series = income_by_months(months)

    return render_template(
        "dashboard.html",
        period=period,
        periods=PERIODS,
        kpis={
            "income_plan": income_plan,
            "income_actual": income_actual,
            "expense_plan": expense_plan,
            "expense_actual": expense_actual,
            "free": free,
            "saved": saved,
        },
        expense_chart=expense_chart,
        income_chart={
            "labels": income_labels,
            "plan": income_plan_series,
            "fact": income_fact_series,
        },
        envelopes=envelope_progress("week", ref),
        upcoming=upcoming_income(ref),
    )
