from datetime import date

from flask import Blueprint, render_template

from db import get_setting
from services.analytics import (
    budget_fact_from_goals,
    budget_fact_own,
    envelope_progress,
    expenses_by_category,
    free_cash_flow,
    generate_smart_insights,
    health_metrics,
    income_by_months,
    income_fact,
    savings_total,
    upcoming_income,
)
from services.constants import DASHBOARD_PERIODS
from services.dates import last_n_months, parse_date, period_bounds
from services.debts import debt_balance, get_friends_money_card, get_uncategorized_debts
from services.forms import parse_period_arg
from services.planning import budget_planned_for_period, income_planned_for_period
from services.reconcile import calculate_expected, get_last_check

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

    # Деньги сейчас (CashNow: расчетный остаток на сегодня с даты последней сверки)
    savings_in_check = int(get_setting("savings_in_check", "1"))
    if last_check:
        exp_info = calculate_expected(0.0, str(ref))
        cash_now = exp_info.get("expected_byn")
    else:
        cash_now = None

    hm = health_metrics(start, end, ref)
    insights = generate_smart_insights(ref)

    # J5 & J7: Неразнесённое и Деньги у друзей
    uncat_debts = get_uncategorized_debts()
    envelopes_data = envelope_progress("week", ref)
    neg_envelopes = [e for e in envelopes_data if e.get("offset_without_expense")]
    uncat_total = len(uncat_debts) + len(neg_envelopes)
    friends_card = get_friends_money_card()

    return render_template(
        "dashboard.html",
        period=period,
        periods=DASHBOARD_PERIODS,
        cash_now=cash_now,
        savings_in_check=savings_in_check,
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
        friends_card=friends_card,
        uncategorized_count=uncat_total,
        check_card={
            "is_stale": is_stale,
            "days_ago": days_ago,
            "text": chk_text,
        },
        health=hm,
        insights=insights[:2],
        expense_chart=expenses_by_category(chart_start, chart_end),
        income_chart={"labels": labels, "plan": plan_series, "fact": fact_series},
        envelopes=envelopes_data,
        upcoming=upcoming_income(ref),
    )
