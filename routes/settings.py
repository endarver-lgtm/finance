from flask import Blueprint, flash, redirect, render_template, request, url_for

from db.settings import get_setting, set_setting
from services.currency import DEFAULT_EUR_RATE, DEFAULT_USD_RATE

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
        flash("Настройки сохранены", "success")
        return redirect(url_for("settings.index"))
    return render_template(
        "settings.html",
        usd_rate=get_setting("usd_rate", str(DEFAULT_USD_RATE)),
        eur_rate=get_setting("eur_rate", str(DEFAULT_EUR_RATE)),
    )
