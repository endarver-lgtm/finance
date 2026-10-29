from datetime import date, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for

from db import get_db, rows_to_dicts
from services.constants import BUDGET_PERIODS
from services.currency import to_byn
from services.dates import add_months, parse_date, period_bounds, period_caption, to_iso
from services.forms import (
    parse_currency,
    parse_entry_fields,
    parse_money,
    parse_period_arg,
)
from services.planning import category_planned_for_period
from services.progress import progress_color, usage_percent
from services.repository import (
    create_budget_category,
    create_budget_entry,
    list_budget_categories,
    sum_in_range_byn,
)

bp = Blueprint("budget", __name__, url_prefix="/budget")


def _budget_ref() -> date:
    ref_s = request.args.get("ref", "").strip()
    if ref_s:
        try:
            return parse_date(ref_s)
        except Exception:
            pass
    return date.today()


@bp.route("/")
def index():
    period = parse_period_arg(BUDGET_PERIODS, "week")
    ref = _budget_ref()
    start, end = period_bounds(period, ref)
    today = date.today()
    is_current = (start <= today <= end)

    if period == "week":
        prev_ref = ref - timedelta(days=7)
        next_ref = ref + timedelta(days=7)
    else:
        prev_ref = add_months(ref, -1)
        next_ref = add_months(ref, 1)

    nav = {
        "prev": url_for("budget.index", period=period, ref=to_iso(prev_ref)),
        "next": url_for("budget.index", period=period, ref=to_iso(next_ref)),
        "today": url_for("budget.index", period=period),
        "is_current": is_current,
    }

    cards = []
    with get_db() as conn:
        for c in list_budget_categories():
            cur = c.get("currency", "BYN")
            planned = category_planned_for_period(c, period)
            planned_byn = to_byn(planned, cur)
            spent = sum_in_range_byn(
                "budget_entries",
                "date",
                start,
                end,
                "category_id = ? AND from_goal_id IS NULL",
                (c["id"],),
            )
            is_track = bool(c.get("track_only"))
            pct = 0.0 if is_track else usage_percent(spent, planned_byn)

            entries = rows_to_dicts(
                conn.execute(
                    """
                    SELECT id, amount, currency, date, comment
                    FROM budget_entries
                    WHERE category_id = ? AND date >= ? AND date <= ? AND from_goal_id IS NULL
                    ORDER BY date DESC, id DESC
                    """,
                    (c["id"], to_iso(start), to_iso(end)),
                ).fetchall()
            )

            cards.append({
                **c,
                "planned_period": planned,
                "planned_currency": cur,
                "spent": spent,
                "spent_currency": "BYN",
                "remaining": max(0, planned_byn - spent) if not is_track else 0.0,
                "pct": pct,
                "color": progress_color(pct) if not is_track else "",
                "track_only": is_track,
                "entries": entries,
            })

    cards.sort(
        key=lambda x: (
            1 if x.get("track_only") or x.get("is_system") or x.get("name") == "Неучтёнка" else 0,
            x.get("name", ""),
        )
    )

    return render_template(
        "budget.html",
        period=period,
        periods=BUDGET_PERIODS,
        categories=cards,
        period_caption=period_caption(period, ref),
        period_start=start,
        period_end=end,
        nav=nav,
        today=today,
    )


@bp.route("/category/add", methods=["POST"])
def add_category():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Укажите название категории", "error")
        return redirect(url_for("budget.index"))
    create_budget_category(
        name,
        parse_money("planned_amount"),
        request.form.get("period", "week"),
        parse_currency(),
    )
    flash("Категория добавлена", "success")
    return redirect(url_for("budget.index", period=request.form.get("view_period", "week")))


@bp.route("/entry/add", methods=["POST"])
def add_entry():
    amount, entry_date, comment, currency = parse_entry_fields()
    period = request.form.get("period", "week")
    split = request.form.get("split") in ("1", "true", "on", "yes")

    cat_id_raw = request.form.get("category_id")
    category_id = int(cat_id_raw) if cat_id_raw and cat_id_raw.isdigit() else None

    if split:
        from services.debts import add_split

        paid_by = request.form.get("paid_by", "me")
        person = request.form.get("person", "").strip()
        my_share_val = request.form.get("my_share")
        if my_share_val is not None and my_share_val.strip() != "":
            my_share = float(my_share_val)
        else:
            my_share = round(amount / 2.0, 2)
        try:
            add_split(
                total_amount=amount,
                currency=currency,
                entry_date=entry_date,
                paid_by=paid_by,
                person=person,
                my_share=my_share,
                category_id=category_id,
                comment=comment,
            )
            flash("Списание разделено и сохранено", "success")
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("budget.index", period=period))
    else:
        if not category_id:
            flash("Укажите категорию", "error")
            return redirect(url_for("budget.index", period=period))
        create_budget_entry(
            category_id,
            amount,
            entry_date,
            comment,
            currency,
        )
        flash("Списание записано", "success")

    return redirect(url_for("budget.index", period=period))
