from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for

from database import get_db, now_iso
from services.dates import last_n_months, parse_date, period_bounds, to_iso
from services.queries import income_by_months

bp = Blueprint("income", __name__, url_prefix="/income")

PERIODS = {"day": "День", "week": "Неделя", "month": "Месяц", "year": "Год"}
TYPE_LABELS = {"regular": "Регулярный", "one_time": "Разовый"}
FREQ_LABELS = {"weekly": "Еженедельно", "monthly": "Ежемесячно", "one_time": "Разово"}


@bp.route("/")
def index():
    period = request.args.get("period", "month")
    if period not in PERIODS:
        period = "month"
    start, end = period_bounds(period, date.today())

    with get_db() as conn:
        sources = conn.execute(
            "SELECT * FROM income_sources ORDER BY active DESC, name"
        ).fetchall()

    cards = []
    for s in sources:
        s = dict(s)
        with get_db() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(amount), 0) AS t FROM income_entries
                WHERE source_id = %s AND date >= %s AND date <= %s
                """,
                (s["id"], to_iso(start), to_iso(end)),
            ).fetchone()
        fact = float(row["t"])
        planned = float(s["planned_amount"])
        if s["frequency"] == "weekly" and period == "month":
            planned *= 4
        elif s["frequency"] == "weekly" and period == "year":
            planned *= 52
        status = "received" if fact >= planned and planned > 0 else (
            "partial" if fact > 0 else "pending"
        )
        cards.append({**s, "fact": fact, "planned_period": planned, "status": status})

    months = last_n_months(6)
    labels, plan, fact = income_by_months(months)

    return render_template(
        "income.html",
        period=period,
        periods=PERIODS,
        sources=cards,
        type_labels=TYPE_LABELS,
        freq_labels=FREQ_LABELS,
        chart={"labels": labels, "plan": plan, "fact": fact},
    )


@bp.route("/source/add", methods=["POST"])
def add_source():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Укажите название источника", "error")
        return redirect(url_for("income.index"))
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO income_sources (name, type, planned_amount, frequency, active, created_at)
            VALUES (%s, %s, %s, %s, 1, %s)
            """,
            (
                name,
                request.form.get("type", "regular"),
                float(request.form.get("planned_amount") or 0),
                request.form.get("frequency", "monthly"),
                now_iso(),
            ),
        )
    flash("Источник добавлен", "success")
    return redirect(url_for("income.index", period=request.form.get("period", "month")))


@bp.route("/entry/add", methods=["POST"])
def add_entry():
    source_id = request.form.get("source_id")
    amount = float(request.form.get("amount") or 0)
    d = parse_date(request.form.get("date") or date.today().isoformat())
    comment = request.form.get("comment", "").strip()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO income_entries (source_id, amount, date, comment, created_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (int(source_id) if source_id else None, amount, to_iso(d), comment or None, now_iso()),
        )
    flash("Поступление записано", "success")
    return redirect(url_for("income.index", period=request.form.get("period", "month")))


@bp.route("/one-time/add", methods=["POST"])
def add_one_time():
    amount = float(request.form.get("amount") or 0)
    d = parse_date(request.form.get("date") or date.today().isoformat())
    comment = request.form.get("comment", "").strip()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO income_entries (source_id, amount, date, comment, created_at)
            VALUES (NULL, %s, %s, %s, %s)
            """,
            (amount, to_iso(d), comment or None, now_iso()),
        )
    flash("Разовый доход добавлен", "success")
    return redirect(url_for("income.index"))
