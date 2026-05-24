from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for

from services.analytics import income_by_months
from services.constants import (
    DASHBOARD_PERIODS,
    INCOME_FREQ_LABELS,
    INCOME_TYPE_LABELS,
)
from services.dates import last_n_months, period_bounds
from services.forms import parse_entry_fields, parse_period_arg
from services.planning import source_planned_for_period
from services.progress import income_status
from services.repository import (
    create_income_entry,
    create_income_source,
    list_income_sources_with_fact,
)

bp = Blueprint("income", __name__, url_prefix="/income")


@bp.route("/")
def index():
    period = parse_period_arg(DASHBOARD_PERIODS, "month")
    start, end = period_bounds(period, date.today())

    cards = []
    for s in list_income_sources_with_fact(start, end):
        planned = source_planned_for_period(s, period)
        fact = float(s["fact"])
        cards.append({
            **s,
            "fact": fact,
            "planned_period": planned,
            "status": income_status(fact, planned),
        })

    labels, plan, fact = income_by_months(last_n_months(6))

    return render_template(
        "income.html",
        period=period,
        periods=DASHBOARD_PERIODS,
        sources=cards,
        type_labels=INCOME_TYPE_LABELS,
        freq_labels=INCOME_FREQ_LABELS,
        chart={"labels": labels, "plan": plan, "fact": fact},
    )


@bp.route("/source/add", methods=["POST"])
def add_source():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Укажите название источника", "error")
        return redirect(url_for("income.index"))
    create_income_source(
        name,
        request.form.get("type", "regular"),
        float(request.form.get("planned_amount") or 0),
        request.form.get("frequency", "monthly"),
    )
    flash("Источник добавлен", "success")
    return redirect(url_for("income.index", period=request.form.get("period", "month")))


@bp.route("/entry/add", methods=["POST"])
def add_entry():
    source_id = request.form.get("source_id")
    amount, entry_date, comment = parse_entry_fields()
    create_income_entry(
        int(source_id) if source_id else None,
        amount,
        entry_date,
        comment,
    )
    flash("Поступление записано", "success")
    return redirect(url_for("income.index", period=request.form.get("period", "month")))


@bp.route("/one-time/add", methods=["POST"])
def add_one_time():
    amount, entry_date, comment = parse_entry_fields()
    create_income_entry(None, amount, entry_date, comment)
    flash("Разовый доход добавлен", "success")
    return redirect(url_for("income.index"))
