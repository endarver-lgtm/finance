from flask import Blueprint, flash, redirect, render_template, request, url_for

from db.settings import get_setting, set_setting
from services.currency import DEFAULT_USD_RATE

bp = Blueprint("settings", __name__, url_prefix="/settings")


@bp.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        try:
            rate = float(request.form.get("usd_rate", DEFAULT_USD_RATE))
            if rate <= 0:
                raise ValueError
        except ValueError:
            flash("Курс должен быть положительным числом (BYN за 1 USD)", "error")
            return redirect(url_for("settings.index"))
        set_setting("currency", "BYN")
        set_setting("usd_rate", str(rate))
        flash("Настройки сохранены", "success")
        return redirect(url_for("settings.index"))
    return render_template(
        "settings.html",
        usd_rate=get_setting("usd_rate", str(DEFAULT_USD_RATE)),
    )
