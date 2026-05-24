from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for

from database import get_db, now_iso
from services.dates import format_date, parse_date, to_iso
from services.queries import goal_saved

bp = Blueprint("savings", __name__, url_prefix="/savings")

TYPE_GROUPS = {
    "want": "Хотелки",
    "reserve": "Резерв",
    "big": "Крупные цели",
}
TYPE_LABELS = TYPE_GROUPS


@bp.route("/")
def index():
    with get_db() as conn:
        goals = conn.execute(
            "SELECT * FROM savings_goals ORDER BY type, name"
        ).fetchall()

    grouped = {k: [] for k in TYPE_GROUPS}
    for g in goals:
        g = dict(g)
        saved = goal_saved(g["id"])
        target = float(g["target_amount"])
        remaining = max(0, target - saved)
        pct = min(100, round(saved / target * 100, 1)) if target > 0 else 0
        with get_db() as conn:
            history = conn.execute(
                """
                SELECT * FROM savings_entries
                WHERE goal_id = %s
                ORDER BY date DESC, id DESC
                """,
                (g["id"],),
            ).fetchall()
        g.update({
            "saved": saved,
            "remaining": remaining,
            "pct": pct,
            "history": [dict(h) for h in history],
        })
        grouped[g["type"]].append(g)

    return render_template(
        "savings.html",
        grouped=grouped,
        type_groups=TYPE_GROUPS,
    )


@bp.route("/goal/add", methods=["POST"])
def add_goal():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Укажите название цели", "error")
        return redirect(url_for("savings.index"))
    deadline = request.form.get("deadline", "").strip()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO savings_goals (name, type, target_amount, deadline, created_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                name,
                request.form.get("type", "want"),
                float(request.form.get("target_amount") or 0),
                deadline or None,
                now_iso(),
            ),
        )
    flash("Цель добавлена", "success")
    return redirect(url_for("savings.index"))


@bp.route("/entry/add", methods=["POST"])
def add_entry():
    goal_id = int(request.form.get("goal_id"))
    amount = float(request.form.get("amount") or 0)
    d = parse_date(request.form.get("date") or date.today().isoformat())
    comment = request.form.get("comment", "").strip()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO savings_entries (goal_id, amount, date, comment, created_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (goal_id, amount, to_iso(d), comment or None, now_iso()),
        )
    flash("Пополнение записано", "success")
    return redirect(url_for("savings.index"))
