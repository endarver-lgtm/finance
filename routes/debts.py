from flask import Blueprint, flash, redirect, render_template, request, url_for

from db import get_setting
from services.debts import (
    add_debt_entry,
    balance_total,
    debt_balance,
    delete_debt,
    list_debt_persons,
    list_debts,
    update_debt,
)
from services.forms import parse_entry_fields

bp = Blueprint("debts", __name__, url_prefix="/debts")


@bp.route("/")
def index():
    selected_person = request.args.get("person", "").strip()
    persons = list_debt_persons()
    default_person = get_setting("default_debt_person", "Кент")
    active_person = selected_person or (persons[0] if persons else default_person)

    rows = list_debts(active_person if selected_person else None)
    p_balance = debt_balance(active_person)
    tot_balance = balance_total()

    return render_template(
        "debts.html",
        persons=persons,
        active_person=active_person,
        selected_person=selected_person,
        person_balance=p_balance,
        total_balance=tot_balance,
        debts=rows,
        default_person=default_person,
    )


@bp.route("/entry/add", methods=["POST"])
def add_entry():
    try:
        person = request.form.get("person", "").strip()
        kind = request.form.get("kind", "").strip()
        amount, entry_date, comment, currency = parse_entry_fields()
        add_debt_entry(person, kind, amount, currency, entry_date, comment)
        flash("Запись по долгу сохранена", "success")
        return redirect(url_for("debts.index", person=person))
    except ValueError as e:
        flash(str(e), "error")
    except Exception as e:
        flash(f"Ошибка при сохранении: {e}", "error")
    return redirect(url_for("debts.index"))


@bp.route("/entry/delete/<int:debt_id>", methods=["POST"])
def delete_entry_route(debt_id: int):
    try:
        if delete_debt(debt_id):
            flash("Запись удалена", "success")
        else:
            flash("Запись не найдена", "error")
    except Exception as e:
        flash(f"Ошибка при удалении: {e}", "error")
    return redirect(request.referrer or url_for("debts.index"))


@bp.route("/entry/edit/<int:debt_id>", methods=["POST"])
def edit_entry(debt_id: int):
    try:
        person = request.form.get("person", "").strip()
        kind = request.form.get("kind", "").strip()
        amount, entry_date, comment, currency = parse_entry_fields()
        update_debt(debt_id, person, kind, amount, currency, entry_date, comment)
        flash("Запись по долгу обновлена", "success")
    except Exception as e:
        flash(f"Ошибка при обновлении: {e}", "error")
    return redirect(request.referrer or url_for("debts.index", person=request.form.get("person")))
