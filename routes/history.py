from flask import Blueprint, render_template, request

from services.analytics import history_rows
from services.constants import HISTORY_KIND_LABELS
from services.dates import format_date, parse_date
from services.repository import list_history_category_names

bp = Blueprint("history", __name__, url_prefix="/history")


@bp.route("/")
def index():
    date_from_s = request.args.get("date_from", "")
    date_to_s = request.args.get("date_to", "")
    type_filter = request.args.get("type", "")
    category_filter = request.args.get("category", "")

    date_from = parse_date(date_from_s) if date_from_s else None
    date_to = parse_date(date_to_s) if date_to_s else None
    rows = history_rows(date_from, date_to, type_filter, category_filter)

    display_rows = [
        {
            **r,
            "date_fmt": format_date(parse_date(r["date"])),
            "kind_label": HISTORY_KIND_LABELS[r["kind"]],
        }
        for r in rows
    ]

    total_income = sum(r["amount"] for r in rows if r["kind"] == "income")
    total_expense = sum(r["amount"] for r in rows if r["kind"] == "expense")
    total_savings = sum(r["amount"] for r in rows if r["kind"] == "savings")

    return render_template(
        "history.html",
        rows=display_rows,
        categories=list_history_category_names(),
        filters={
            "date_from": date_from_s,
            "date_to": date_to_s,
            "type": type_filter,
            "category": category_filter,
        },
        totals={
            "income": total_income,
            "expense": total_expense,
            "savings": total_savings,
            "net": total_income - total_expense,
        },
        kind_labels=HISTORY_KIND_LABELS,
    )
