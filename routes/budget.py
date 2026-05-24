from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for

from services.constants import BUDGET_PERIODS
from services.dates import period_bounds
from services.forms import parse_entry_fields, parse_period_arg
from services.planning import category_planned_for_period
from services.progress import progress_color, usage_percent
from services.repository import (
    create_budget_category,
    create_budget_entry,
    list_budget_categories,
    list_budget_entries,
    sum_in_range,
)

bp = Blueprint("budget", __name__, url_prefix="/budget")


@bp.route("/")
def index():
    period = parse_period_arg(BUDGET_PERIODS, "week")
    start, end = period_bounds(period, date.today())

    cards = []
    for c in list_budget_categories():
        planned = category_planned_for_period(c, period)
        spent = sum_in_range(
            "budget_entries",
            "amount",
            "date",
            start,
            end,
            "category_id = ?",
            (c["id"],),
        )
        pct = usage_percent(spent, planned)
        cards.append({
            **c,
            "planned_period": planned,
            "spent": spent,
            "remaining": max(0, planned - spent),
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
        float(request.form.get("planned_amount") or 0),
        request.form.get("period", "week"),
    )
    flash("Категория добавлена", "success")
    return redirect(url_for("budget.index", period=request.form.get("view_period", "week")))


@bp.route("/entry/add", methods=["POST"])
def add_entry():
    amount, entry_date, comment = parse_entry_fields()
    create_budget_entry(
        int(request.form.get("category_id")),
        amount,
        entry_date,
        comment,
    )
    flash("Списание записано", "success")
    return redirect(url_for("budget.index", period=request.form.get("period", "week")))
