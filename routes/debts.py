import json
from datetime import date
from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from db import get_setting
from services.debts import (
    add_debt_entry,
    balance_total,
    debt_balance,
    delete_debt,
    find_candidate_expenses,
    get_friends_money_card,
    get_uncategorized_debts,
    list_debt_persons,
    list_debts,
    suggest_matches_for_debts,
    update_debt,
)
from services.forms import parse_entry_fields
from services.repository import list_budget_categories

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

    categories = list_budget_categories()
    friends_card = get_friends_money_card()
    uncategorized = get_uncategorized_debts()
    suggestions = suggest_matches_for_debts()

    return render_template(
        "debts.html",
        persons=persons,
        active_person=active_person,
        selected_person=selected_person,
        person_balance=p_balance,
        total_balance=tot_balance,
        debts=rows,
        default_person=default_person,
        categories=categories,
        friends_card=friends_card,
        uncategorized_count=len(uncategorized),
        suggestions=suggestions,
        today=date.today(),
    )


@bp.route("/entry/add", methods=["POST"])
def add_entry():
    try:
        person = request.form.get("person", "").strip()
        kind = request.form.get("kind", "").strip()
        category_id = request.form.get("category_id")
        offset_date = request.form.get("offset_date")
        expense_id = request.form.get("expense_id")
        amount, entry_date, comment, currency = parse_entry_fields()

        add_debt_entry(
            person=person,
            kind=kind,
            amount=amount,
            currency=currency,
            entry_date=entry_date,
            comment=comment,
            category_id=int(category_id) if category_id and category_id.isdigit() else None,
            offset_date=offset_date,
            expense_id=int(expense_id) if expense_id and expense_id.isdigit() else None,
            source="manual",
        )
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
        category_id = request.form.get("category_id")
        offset_date = request.form.get("offset_date")
        expense_id = request.form.get("expense_id")
        amount, entry_date, comment, currency = parse_entry_fields()

        update_debt(
            debt_id=debt_id,
            person=person,
            kind=kind,
            amount=amount,
            currency=currency,
            entry_date=entry_date,
            comment=comment,
            category_id=int(category_id) if category_id and category_id.isdigit() else None,
            offset_date=offset_date,
            expense_id=int(expense_id) if expense_id and expense_id.isdigit() else None,
        )
        flash("Запись по долгу обновлена", "success")
    except Exception as e:
        flash(f"Ошибка при обновлении: {e}", "error")
    return redirect(request.referrer or url_for("debts.index", person=request.form.get("person")))


@bp.route("/batch_add", methods=["POST"])
def batch_add():
    """J1: Пакетный ввод долгов из заметки."""
    try:
        raw_json = request.form.get("batch_data")
        if raw_json:
            rows = json.loads(raw_json)
        else:
            rows = request.get_json(silent=True) or []

        count = 0
        for r in rows:
            person = str(r.get("person") or "").strip()
            amount = float(r.get("amount") or 0)
            if not person or amount <= 0:
                continue
            cat_id = r.get("category_id")
            cat_val = int(cat_id) if cat_id and str(cat_id).isdigit() else None
            entry_date = str(r.get("date") or date.today().isoformat()).strip()
            kind = str(r.get("kind") or "i_paid").strip()
            comment = str(r.get("comment") or "").strip()
            currency = str(r.get("currency") or "BYN").strip()

            add_debt_entry(
                person=person,
                kind=kind,
                amount=amount,
                currency=currency,
                entry_date=entry_date,
                comment=comment,
                category_id=cat_val,
                offset_date=entry_date,
                source="manual",
            )
            count += 1

        flash(f"Добавлено записей: {count}", "success")
    except Exception as e:
        flash(f"Ошибка пакетного ввода: {e}", "error")
    return redirect(url_for("debts.index"))


@bp.route("/candidates")
def candidates_api():
    """J4: API кандидатов для связывания расхода с долгом."""
    cat_id = request.args.get("category_id")
    target_date = request.args.get("date") or date.today().isoformat()
    amount = float(request.args.get("amount") or 0.0)
    cid = int(cat_id) if cat_id and cat_id.isdigit() else None
    items = find_candidate_expenses(cid, target_date, amount)
    return jsonify({"candidates": items})


@bp.route("/link", methods=["POST"])
def link_debt():
    """J5: Связывание долга с расходом / категорией."""
    try:
        debt_id = int(request.form.get("debt_id"))
        category_id = request.form.get("category_id")
        expense_id = request.form.get("expense_id")
        offset_date = request.form.get("offset_date")

        from db import get_db
        with get_db() as conn:
            debt = conn.execute("SELECT * FROM debts WHERE id = ?", (debt_id,)).fetchone()
            if not debt:
                flash("Долг не найден", "error")
                return redirect(url_for("debts.index"))

        update_debt(
            debt_id=debt_id,
            person=debt["person"],
            kind=debt["kind"],
            amount=debt["amount"],
            currency=debt["currency"],
            entry_date=debt["date"],
            comment=debt["comment"],
            category_id=int(category_id) if category_id and category_id.isdigit() else None,
            offset_date=offset_date or debt["date"],
            expense_id=int(expense_id) if expense_id and expense_id.isdigit() else None,
        )
        flash("Долг успешно связан с категорией", "success")
    except Exception as e:
        flash(f"Ошибка при связывании: {e}", "error")
    return redirect(request.referrer or url_for("debts.index"))
