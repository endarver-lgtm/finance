from datetime import date

from flask import Blueprint, render_template, request

from services.dates import format_date, parse_date
from services.queries import history_rows

bp = Blueprint("history", __name__, url_prefix="/history")

KIND_LABELS = {
    "income": "Приход",
    "expense": "Расход",
    "savings": "Накопление",
}


@bp.route("/")
def index():
    date_from_s = request.args.get("date_from", "")
    date_to_s = request.args.get("date_to", "")
    type_filter = request.args.get("type", "")
    category_filter = request.args.get("category", "")

    date_from = parse_date(date_from_s) if date_from_s else None
    date_to = parse_date(date_to_s) if date_to_s else None

    rows = history_rows(date_from, date_to, type_filter, category_filter)

    from database import get_db

    categories = set()
    with get_db() as conn:
        for r in conn.execute("SELECT name FROM income_sources").fetchall():
            categories.add(r["name"])
        categories.add("Разовый доход")
        for r in conn.execute("SELECT name FROM budget_categories").fetchall():
            categories.add(r["name"])
        for r in conn.execute("SELECT name FROM savings_goals").fetchall():
            categories.add(r["name"])
    categories = sorted(categories)
    total_income = sum(r["amount"] for r in rows if r["kind"] == "income")
    total_expense = sum(r["amount"] for r in rows if r["kind"] == "expense")
    total_savings = sum(r["amount"] for r in rows if r["kind"] == "savings")

    display_rows = []
    for r in rows:
        d = parse_date(r["date"])
        display_rows.append({
            **r,
            "date_fmt": format_date(d),
            "kind_label": KIND_LABELS[r["kind"]],
        })

    return render_template(
        "history.html",
        rows=display_rows,
        categories=categories,
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
        kind_labels=KIND_LABELS,
    )
