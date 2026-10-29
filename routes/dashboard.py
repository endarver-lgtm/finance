from datetime import date

from flask import Blueprint, render_template

from db import get_setting
from services.analytics import (
    budget_fact_from_goals,
    budget_fact_own,
    envelope_progress,
    expenses_by_category,
    free_cash_flow,
    income_by_months,
    income_fact,
    savings_total,
    upcoming_income,
)
from services.constants import DASHBOARD_PERIODS
from services.dates import last_n_months, parse_date, period_bounds
from services.debts import debt_balance
from services.forms import parse_period_arg
from services.planning import budget_planned_for_period, income_planned_for_period
from services.reconcile import get_last_check

bp = Blueprint("dashboard", __name__, url_prefix="/")


@bp.route("/")
def index():
    period = parse_period_arg(DASHBOARD_PERIODS, "month")
    ref = date.today()
    start, end = period_bounds(period, ref)

    chart_start, chart_end = period_bounds("month", ref)
    months = last_n_months(6, ref)
    labels, plan_series, fact_series = income_by_months(months)

    # Долги
    default_person = get_setting("default_debt_person", "Кент")
    d_bal = debt_balance(default_person)
    if d_bal > 0.005:
        d_text = f"{default_person} должен мне {d_bal:.2f} BYN"
    elif d_bal < -0.005:
        d_text = f"Я должен {default_person} {abs(d_bal):.2f} BYN"
    else:
        d_text = "Расчёт закрыт"

    # Сверка
    last_check = get_last_check()
    if last_check:
        chk_date = parse_date(last_check["date"])
        days_ago = (date.today() - chk_date).days if chk_date else 0
        is_stale = days_ago > 7
        if days_ago == 0:
            chk_text = "Сверка была сегодня"
        elif days_ago == 1:
            chk_text = "Сверка была вчера"
        else:
            chk_text = f"Сверка {days_ago} дн. назад"
    else:
        is_stale = True
        days_ago = None
        chk_text = "Сверок ещё не было"

    return render_template(
        "dashboard.html",
        period=period,
        periods=DASHBOARD_PERIODS,
        kpis={
            "income_plan": income_planned_for_period(period, ref),
            "income_actual": income_fact(start, end),
            "expense_plan": budget_planned_for_period(period, ref),
            "expense_actual": budget_fact_own(start, end),
            "expense_from_goals": budget_fact_from_goals(start, end),
            "free": free_cash_flow(start, end),
            "saved": savings_total(),
        },
        debt_card={
            "person": default_person,
            "balance": d_bal,
            "text": d_text,
        },
        check_card={
            "is_stale": is_stale,
            "days_ago": days_ago,
            "text": chk_text,
        },
        expense_chart=expenses_by_category(chart_start, chart_end),
        income_chart={"labels": labels, "plan": plan_series, "fact": fact_series},
        envelopes=envelope_progress("week", ref),
        upcoming=upcoming_income(ref),
    )

