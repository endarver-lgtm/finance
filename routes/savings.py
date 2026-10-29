from flask import Blueprint, flash, redirect, render_template, request, url_for

from services.constants import SAVINGS_TYPE_GROUPS
from services.forms import parse_currency, parse_entry_fields, parse_money
from services.progress import usage_percent
from services.repository import (
    create_savings_entry,
    create_savings_goal,
    list_budget_categories,
    list_savings_goals,
    sum_savings_for_goal,
)
from services.savings import (
    delete_savings_entry,
    list_savings_entries_detailed,
    withdraw_from_goal,
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
            "history": list_savings_entries_detailed(g["id"]),
        })

    return render_template(
        "savings.html",
        grouped=grouped,
        type_groups=SAVINGS_TYPE_GROUPS,
        categories=list_budget_categories(),
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


@bp.route("/entry/withdraw", methods=["POST"])
def withdraw():
    try:
        goal_id = int(request.form.get("goal_id"))
        amount, entry_date, comment, currency = parse_entry_fields()
        purpose = request.form.get("purpose", "spent")
        category_id = request.form.get("category_id")
        cat_id = int(category_id) if category_id and category_id.isdigit() else None
        withdraw_from_goal(goal_id, amount, currency, entry_date, purpose, cat_id, comment)
        flash("Снятие записано", "success")
    except ValueError as e:
        flash(str(e), "error")
    except Exception as e:
        flash(f"Ошибка при снятии: {e}", "error")
    return redirect(url_for("savings.index"))


@bp.route("/entry/delete/<int:entry_id>", methods=["POST"])
def delete_entry_route(entry_id: int):
    try:
        if delete_savings_entry(entry_id):
            flash("Запись удалена", "success")
        else:
            flash("Запись не найдена", "error")
    except Exception as e:
        flash(f"Ошибка при удалении: {e}", "error")
    return redirect(url_for("savings.index"))

