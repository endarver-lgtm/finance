from datetime import date
from flask import Blueprint, flash, redirect, render_template, request, url_for

from db import get_setting
from services.dates import parse_date
from services.reconcile import calculate_expected, get_last_check, list_balance_checks, save_check

bp = Blueprint("balance", __name__, url_prefix="/balance")


@bp.route("/")
def index():
    last_check = get_last_check()
    checks = list_balance_checks()
    savings_in_check = int(get_setting("savings_in_check", "1"))

    # Ожидаемый остаток на сегодня относительно последней сверки
    preview = None
    if last_check:
        today_iso = date.today().isoformat()
        preview = calculate_expected(last_check["real_byn"], today_iso)

    return render_template(
        "balance.html",
        last_check=last_check,
        checks=checks,
        savings_in_check=savings_in_check,
        preview=preview,
    )


@bp.route("/check", methods=["POST"])
def check_balance():
    try:
        byn_s = request.form.get("byn", "").strip()
        usd_s = request.form.get("usd", "").strip()
        eur_s = request.form.get("eur", "").strip()

        if not byn_s and not usd_s and not eur_s:
            flash("Укажите сумму хотя бы в одной валюте (наличные или карты)", "error")
            return redirect(url_for("balance.index"))

        byn = float(byn_s) if byn_s else 0.0
        usd = float(usd_s) if usd_s else 0.0
        eur = float(eur_s) if eur_s else 0.0

        if byn < 0 or usd < 0 or eur < 0:
            flash("Суммы не могут быть отрицательными", "error")
            return redirect(url_for("balance.index"))

        check_date = request.form.get("date", "").strip() or date.today().isoformat()
        resolution = request.form.get("resolution", "default").strip()
        comment = request.form.get("comment", "").strip() or None

        res = save_check(
            {"byn": byn, "usd": usd, "eur": eur},
            check_date=check_date,
            resolution=resolution,
            comment=comment,
        )

        diff = res.get("diff_byn")
        if diff is None:
            flash("Базовая точка сверки успешно сохранена", "success")
        elif abs(diff) <= 0.5:
            flash("Сверка завершена: фактический остаток сходится с расчётным!", "success")
        elif diff < 0:
            if res.get("adjust_expense_id"):
                flash(
                    f"Сверка сохранена. Недостача {abs(diff):.2f} BYN списана в категорию «Неучтёнка»",
                    "warning",
                )
            else:
                flash(
                    f"Сверка сохранена. Зафиксировано расхождение: недостача {abs(diff):.2f} BYN",
                    "warning",
                )
        else:
            if res.get("adjust_income_id"):
                flash(
                    f"Сверка сохранена. Излишек {diff:.2f} BYN записан как разовый приход",
                    "success",
                )
            else:
                flash(
                    f"Сверка сохранена. Зафиксировано расхождение: излишек {diff:.2f} BYN",
                    "warning",
                )

    except ValueError as e:
        flash(str(e), "error")
    except Exception as e:
        flash(f"Ошибка при проведении сверки: {e}", "error")

    return redirect(url_for("balance.index"))
