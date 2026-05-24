from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for

from database import get_db, now_iso
from services.dates import parse_date, period_bounds, to_iso
from services.queries import category_planned_for_period, sum_in_range

bp = Blueprint("budget", __name__, url_prefix="/budget")

PERIODS = {"week": "Неделя", "month": "Месяц"}


def progress_color(pct: float) -> str:
    if pct >= 90:
        return "danger"
    if pct >= 70:
        return "warning"
    return "ok"


@bp.route("/")
def index():
    period = request.args.get("period", "week")
    if period not in PERIODS:
        period = "week"
    start, end = period_bounds(period, date.today())

    with get_db() as conn:
        cats = conn.execute(
            "SELECT * FROM budget_categories ORDER BY name"
        ).fetchall()

    cards = []
    for c in cats:
        c = dict(c)
        planned = category_planned_for_period(c, period)
        spent = sum_in_range(
            "budget_entries", "amount", "date", start, end,
            "category_id = %s", (c["id"],),
        )
        pct = min(100, round(spent / planned * 100, 1)) if planned > 0 else 0
        with get_db() as conn:
            history = conn.execute(
                """
                SELECT * FROM budget_entries
                WHERE category_id = %s
                ORDER BY date DESC, id DESC
                """,
                (c["id"],),
            ).fetchall()
        cards.append({
            **c,
            "planned_period": planned,
            "spent": spent,
            "remaining": max(0, planned - spent),
            "pct": pct,
            "color": progress_color(pct),
            "history": [dict(h) for h in history],
        })

    return render_template(
        "budget.html",
        period=period,
        periods=PERIODS,
        categories=cards,
    )


@bp.route("/category/add", methods=["POST"])
def add_category():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Укажите название категории", "error")
        return redirect(url_for("budget.index"))
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO budget_categories (name, planned_amount, period, created_at)
            VALUES (%s, %s, %s, %s)
            """,
            (
                name,
                float(request.form.get("planned_amount") or 0),
                request.form.get("period", "week"),
                now_iso(),
            ),
        )
    flash("Категория добавлена", "success")
    return redirect(url_for("budget.index", period=request.form.get("view_period", "week")))


@bp.route("/entry/add", methods=["POST"])
def add_entry():
    category_id = int(request.form.get("category_id"))
    amount = float(request.form.get("amount") or 0)
    d = parse_date(request.form.get("date") or date.today().isoformat())
    comment = request.form.get("comment", "").strip()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO budget_entries (category_id, amount, date, comment, created_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (category_id, amount, to_iso(d), comment or None, now_iso()),
        )
    flash("Списание записано", "success")
    return redirect(url_for("budget.index", period=request.form.get("period", "week")))
