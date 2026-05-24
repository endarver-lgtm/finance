import os
from datetime import date

from flask import Flask

from config import DEFAULT_CURRENCY, SECRET_KEY
from db import get_setting, init_db
from services.currency import to_usd, usd_rate


def create_app():
    app = Flask(__name__)
    app.secret_key = SECRET_KEY
    init_db()

    from routes.budget import bp as budget_bp
    from routes.dashboard import bp as dashboard_bp
    from routes.history import bp as history_bp
    from routes.income import bp as income_bp
    from routes.savings import bp as savings_bp
    from routes.settings import bp as settings_bp

    for bp in (dashboard_bp, income_bp, budget_bp, savings_bp, history_bp, settings_bp):
        app.register_blueprint(bp)

    @app.template_filter("to_usd")
    def to_usd_filter(value):
        return "%.2f" % to_usd(value)

    @app.template_filter("db_date")
    def db_date_filter(value):
        if value is None:
            return ""
        if hasattr(value, "strftime"):
            return value.strftime("%d.%m.%Y")
        parts = str(value).split("-")
        if len(parts) == 3:
            return f"{parts[2]}.{parts[1]}.{parts[0]}"
        return str(value)

    @app.context_processor
    def inject_globals():
        rate = usd_rate()
        return {
            "currency": get_setting("currency", DEFAULT_CURRENCY),
            "usd_rate": rate,
            "today": date.today(),
        }

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0").lower() in ("1", "true", "yes")
    app.run(host="127.0.0.1", port=port, debug=debug, use_reloader=debug)
