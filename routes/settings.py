from flask import Blueprint, flash, redirect, render_template, request, url_for

from database import get_setting, set_setting

bp = Blueprint("settings", __name__, url_prefix="/settings")


@bp.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        currency = request.form.get("currency", "€").strip() or "€"
        set_setting("currency", currency)
        flash("Настройки сохранены", "success")
        return redirect(url_for("settings.index"))
    return render_template(
        "settings.html",
        currency=get_setting("currency", "€"),
    )
