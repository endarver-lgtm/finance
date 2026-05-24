import os
from datetime import date

from flask import Flask

from config import DEFAULT_CURRENCY, SECRET_KEY
from database import get_setting, init_db


def create_app():
    app = Flask(__name__)
    app.secret_key = SECRET_KEY

    init_db()

    from routes.dashboard import bp as dashboard_bp
    from routes.income import bp as income_bp
    from routes.budget import bp as budget_bp
    from routes.savings import bp as savings_bp
    from routes.history import bp as history_bp
    from routes.settings import bp as settings_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(income_bp)
    app.register_blueprint(budget_bp)
    app.register_blueprint(savings_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(settings_bp)

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
        return {
            "currency": get_setting("currency", DEFAULT_CURRENCY),
            "today": date.today(),
        }

    return app


def _build_app():
    try:
        return create_app()
    except Exception as exc:
        print("\n[STARTUP ERROR]", exc)
        print("\nCheck .env:")
        print("  - Windows: use Session pooler URI (IPv4), NOT db.*.supabase.co (IPv6 only)")
        print("  - Supabase -> Connect -> copy Session pooler string, port 5432")
        print("  - password URL-encoded if needed (@ -> %40)")
        print("  - internet / VPN off\n")
        raise


app = _build_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0").lower() in ("1", "true", "yes")
    try:
        app.run(host="127.0.0.1", port=port, debug=debug, use_reloader=debug)
    except Exception as exc:
        print("\n[ERROR]", exc)
        raise
