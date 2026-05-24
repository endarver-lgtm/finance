from datetime import date

from flask import Blueprint, render_template

from services.analytics import (
    budget_fact,
    envelope_progress,
    expenses_by_category,
    income_by_months,
    income_fact,
    savings_total,
    upcoming_income,
)
from services.constants import DASHBOARD_PERIODS
from services.dates import last_n_months, period_bounds
from services.forms import parse_period_arg
from services.planning import budget_planned_for_period, income_planned_for_period

bp = Blueprint("dashboard", __name__, url_prefix="/")


@bp.route("/")
def index():
    period = parse_period_arg(DASHBOARD_PERIODS, "month")
    ref = date.today()
    start, end = period_bounds(period, ref)

    chart_start, chart_end = period_bounds("month", ref)
    months = last_n_months(6, ref)
    labels, plan_series, fact_series = income_by_months(months)

    return render_template(
        "dashboard.html",
        period=period,
        periods=DASHBOARD_PERIODS,
        kpis={
            "income_plan": income_planned_for_period(period, ref),
            "income_actual": income_fact(start, end),
            "expense_plan": budget_planned_for_period(period, ref),
            "expense_actual": budget_fact(start, end),
            "free": income_fact(start, end) - budget_fact(start, end),
            "saved": savings_total(),
        },
        expense_chart=expenses_by_category(chart_start, chart_end),
        income_chart={"labels": labels, "plan": plan_series, "fact": fact_series},
        envelopes=envelope_progress("week", ref),
        upcoming=upcoming_income(ref),
    )
