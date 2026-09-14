from flask import Blueprint, flash, redirect, render_template, request, url_for

from services.constants import SAVINGS_TYPE_GROUPS
from services.forms import parse_currency, parse_entry_fields, parse_money
from services.progress import usage_percent
from services.repository import (
    create_savings_entry,
    create_savings_goal,
    list_savings_entries,
    list_savings_goals,
    sum_savings_for_goal,
)

bp = Blueprint("savings", __name__, url_prefix="/savings")


@bp.route("/")
def index():
    grouped = {k: [] for k in SAVINGS_TYPE_GROUPS}
    for g in list_savings_goals():
        cur = g.get("currency", "BYN")
        saved = sum_savings_for_goal(g["id"], cur)
        target = float(g["target_amount"])
        remaining = max(0, target - saved)
        pct = usage_percent(saved, target)
        grouped[g["type"]].append({
            **g,
            "goal_currency": cur,
            "saved": saved,
            "saved_currency": cur,
            "remaining": remaining,
            "pct": pct,
            "history": list_savings_entries(g["id"]),
        })

    return render_template(
        "savings.html",
        grouped=grouped,
        type_groups=SAVINGS_TYPE_GROUPS,
    )


@bp.route("/goal/add", methods=["POST"])
def add_goal():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Укажите название цели", "error")
        return redirect(url_for("savings.index"))
    deadline = request.form.get("deadline", "").strip() or None
    create_savings_goal(
        name,
        request.form.get("type", "want"),
        parse_money("target_amount"),
        deadline,
        parse_currency(),
    )
    flash("Цель добавлена", "success")
    return redirect(url_for("savings.index"))


@bp.route("/entry/add", methods=["POST"])
def add_entry():
    amount, entry_date, comment, currency = parse_entry_fields()
    create_savings_entry(
        int(request.form.get("goal_id")),
        amount,
        entry_date,
        comment,
        currency,
    )
    flash("Пополнение записано", "success")
    return redirect(url_for("savings.index"))
