from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for

from services.constants import BUDGET_PERIODS
from services.currency import to_byn
from services.dates import period_bounds
from services.forms import (
    parse_currency,
    parse_entry_fields,
    parse_money,
    parse_period_arg,
)
from services.planning import category_planned_for_period
from services.progress import progress_color, usage_percent
from services.repository import (
    create_budget_category,
    create_budget_entry,
    list_budget_categories,
    list_budget_entries,
    sum_in_range_byn,
)

bp = Blueprint("budget", __name__, url_prefix="/budget")


@bp.route("/")
def index():
    period = parse_period_arg(BUDGET_PERIODS, "week")
    start, end = period_bounds(period, date.today())

    cards = []
    for c in list_budget_categories():
        cur = c.get("currency", "BYN")
        planned = category_planned_for_period(c, period)
        planned_byn = to_byn(planned, cur)
        spent = sum_in_range_byn(
            "budget_entries",
            "date",
            start,
            end,
            "category_id = ?",
            (c["id"],),
        )
        pct = usage_percent(spent, planned_byn)
        cards.append({
            **c,
            "planned_period": planned,
            "planned_currency": cur,
            "spent": spent,
            "spent_currency": "BYN",
            "remaining": max(0, planned_byn - spent),
            "pct": pct,
            "color": progress_color(pct),
            "history": list_budget_entries(c["id"]),
        })

    return render_template(
        "budget.html",
        period=period,
        periods=BUDGET_PERIODS,
        categories=cards,
    )


@bp.route("/category/add", methods=["POST"])
def add_category():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Укажите название категории", "error")
        return redirect(url_for("budget.index"))
    create_budget_category(
        name,
        parse_money("planned_amount"),
        request.form.get("period", "week"),
        parse_currency(),
    )
    flash("Категория добавлена", "success")
    return redirect(url_for("budget.index", period=request.form.get("view_period", "week")))


@bp.route("/entry/add", methods=["POST"])
def add_entry():
    amount, entry_date, comment, currency = parse_entry_fields()
    create_budget_entry(
        int(request.form.get("category_id")),
        amount,
        entry_date,
        comment,
        currency,
    )
    flash("Списание записано", "success")
    return redirect(url_for("budget.index", period=request.form.get("period", "week")))
