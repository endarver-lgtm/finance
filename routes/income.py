from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for

from services.analytics import income_by_months
from services.constants import (
    DASHBOARD_PERIODS,
    INCOME_FREQ_LABELS,
    INCOME_TYPE_LABELS,
)
from services.currency import to_byn
from services.dates import add_months, last_n_months, month_start, period_bounds, period_caption
from services.forms import parse_currency, parse_entry_fields, parse_money, parse_period_arg
from services.planning import source_planned_for_period
from services.progress import income_status
from services.repository import (
    create_income_entry,
    create_income_source,
    list_income_sources_with_fact,
    sum_orphan_income_byn,
)

bp = Blueprint("income", __name__, url_prefix="/income")


def _period_ref() -> date:
    """Опорная дата для расчёта: календарный месяц/неделя/год от «сегодня» или ?year=&month=."""
    today = date.today()
    period = parse_period_arg(DASHBOARD_PERIODS, "month")
    if period != "month":
        return today
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    if year and month and 1 <= month <= 12:
        return date(year, month, 1)
    return today


def _income_redirect(period: str, ref: date):
    if period == "month":
        return redirect(
            url_for("income.index", period=period, year=ref.year, month=ref.month)
        )
    return redirect(url_for("income.index", period=period))


@bp.route("/")
def index():
    period = parse_period_arg(DASHBOARD_PERIODS, "month")
    ref = _period_ref()
    start, end = period_bounds(period, ref)

    cards = []
    for s in list_income_sources_with_fact(start, end):
        cur = s.get("currency", "BYN")
        planned = source_planned_for_period(s, period)
        fact = float(s["fact"])
        cards.append({
            **s,
            "planned_period": planned,
            "planned_currency": cur,
            "fact": fact,
            "fact_currency": "BYN",
            "status": income_status(fact, to_byn(planned, cur)),
        })

    labels, plan, fact = income_by_months(last_n_months(6, date.today()))
    orphan_fact = sum_orphan_income_byn(start, end)
    period_totals = {
        "planned": round(
            sum(to_byn(c["planned_period"], c.get("planned_currency", "BYN")) for c in cards),
            2,
        ),
        "fact": round(sum(c["fact"] for c in cards) + orphan_fact, 2),
    }

    month_nav = None
    if period == "month":
        cur_month = month_start(ref)
        month_nav = {
            "prev": url_for(
                "income.index",
                period="month",
                year=add_months(cur_month, -1).year,
                month=add_months(cur_month, -1).month,
            ),
            "next": url_for(
                "income.index",
                period="month",
                year=add_months(cur_month, 1).year,
                month=add_months(cur_month, 1).month,
            ),
            "is_current": ref.year == date.today().year and ref.month == date.today().month,
        }

    return render_template(
        "income.html",
        period=period,
        periods=DASHBOARD_PERIODS,
        period_caption=period_caption(period, ref),
        period_start=start,
        period_end=end,
        ref_year=ref.year,
        ref_month=ref.month,
        month_nav=month_nav,
        sources=cards,
        orphan_fact=orphan_fact,
        period_totals=period_totals,
        period_query=(
            f"&year={ref.year}&month={ref.month}" if period == "month" else ""
        ),
        type_labels=INCOME_TYPE_LABELS,
        freq_labels=INCOME_FREQ_LABELS,
        chart={"labels": labels, "plan": plan, "fact": fact},
    )


@bp.route("/source/add", methods=["POST"])
def add_source():
    name = request.form.get("name", "").strip()
    period = request.form.get("period", "month")
    ref = _period_ref_from_form()
    if not name:
        flash("Укажите название источника", "error")
        return _income_redirect(period, ref)
    create_income_source(
        name,
        request.form.get("type", "regular"),
        parse_money("planned_amount"),
        request.form.get("frequency", "monthly"),
        parse_currency(),
    )
    flash("Источник добавлен", "success")
    return _income_redirect(period, ref)


@bp.route("/entry/add", methods=["POST"])
def add_entry():
    source_id = request.form.get("source_id")
    period = request.form.get("period", "month")
    ref = _period_ref_from_form()
    amount, entry_date, comment, currency = parse_entry_fields()
    create_income_entry(
        int(source_id) if source_id else None,
        amount,
        entry_date,
        comment,
        currency,
    )
    flash("Поступление записано", "success")
    return _income_redirect(period, ref)


@bp.route("/one-time/add", methods=["POST"])
def add_one_time():
    amount, entry_date, comment, currency = parse_entry_fields()
    create_income_entry(None, amount, entry_date, comment, currency)
    flash("Разовый доход добавлен", "success")
    period = request.form.get("period", "month")
    return _income_redirect(period, _period_ref_from_form())


def _period_ref_from_form() -> date:
    today = date.today()
    year = request.form.get("year", type=int)
    month = request.form.get("month", type=int)
    if year and month and 1 <= month <= 12:
        return date(year, month, 1)
    return today
