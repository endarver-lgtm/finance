from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from db.settings import get_setting, set_setting
from services.currency import DEFAULT_EUR_RATE, DEFAULT_USD_RATE
from services.nbrb import sync_rates_from_nbrb

bp = Blueprint("settings", __name__, url_prefix="/settings")


@bp.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        try:
            usd = float(request.form.get("usd_rate", DEFAULT_USD_RATE))
            eur = float(request.form.get("eur_rate", DEFAULT_EUR_RATE))
            if usd <= 0 or eur <= 0:
                raise ValueError
        except ValueError:
            flash("Курсы должны быть положительными числами", "error")
            return redirect(url_for("settings.index"))
        set_setting("currency", "BYN")
        set_setting("usd_rate", str(usd))
        set_setting("eur_rate", str(eur))
        set_setting("rates_updated_at", "")  # очищаем отметку НБРБ при ручном вводе
        set_setting("rates_nbrb_date", "")

        savings_in_check = "1" if request.form.get("savings_in_check") in ("1", "on", "true") else "0"
        default_person = request.form.get("default_debt_person", "").strip() or "Кент"
        set_setting("savings_in_check", savings_in_check)
        set_setting("default_debt_person", default_person)

        flash("Настройки сохранены", "success")
        return redirect(url_for("settings.index"))
    return render_template(
        "settings.html",
        usd_rate=get_setting("usd_rate", str(DEFAULT_USD_RATE)),
        eur_rate=get_setting("eur_rate", str(DEFAULT_EUR_RATE)),
        rates_updated_at=get_setting("rates_updated_at", ""),
        rates_nbrb_date=get_setting("rates_nbrb_date", ""),
        savings_in_check=get_setting("savings_in_check", "1"),
        default_debt_person=get_setting("default_debt_person", "Кент"),
    )



@bp.route("/sync-nbrb", methods=["POST"])
def sync_nbrb():
    try:
        res = sync_rates_from_nbrb()
        flash(
            f"Курсы успешно обновлены по данным НБРБ (на {res['nbrb_date']}): "
            f"1 USD = {res['usd_rate']} BYN, 1 EUR = {res['eur_rate']} BYN",
            "success",
        )
    except Exception as e:
        flash(str(e), "error")
    return redirect(url_for("settings.index"))


@bp.route("/api/sync-nbrb", methods=["GET", "POST"])
def api_sync_nbrb():
    try:
        res = sync_rates_from_nbrb()
        return jsonify({"success": True, **res})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
