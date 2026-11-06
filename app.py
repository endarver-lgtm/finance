import os
from datetime import date, timedelta

from flask import Flask, redirect, request, send_from_directory, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from config import DEFAULT_CURRENCY, SECRET_KEY
from db import get_setting, init_db
from services.constants import BASE_CURRENCY, CURRENCIES
from services.currency import eur_rate, to_byn, to_usd, usd_rate
from services.nbrb import refresh_rates_if_stale


def create_app():
    app = Flask(__name__)
    app.secret_key = SECRET_KEY
    app.permanent_session_lifetime = timedelta(days=90)
    
    # Determine if HTTPS should be enforced for cookies
    secure_cookies = (
        os.environ.get("SESSION_COOKIE_SECURE", "0").lower() in ("1", "true")
        or os.environ.get("APP_ENV") == "production"
    )
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=secure_cookies,
    )
    
    # Wrap WSGI app with ProxyFix to trust reverse proxy (Nginx) headers:
    # X-Forwarded-For (client IP), X-Forwarded-Proto (https/http), X-Forwarded-Host, X-Forwarded-Prefix
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=1,
        x_proto=1,
        x_host=1,
        x_prefix=1,
    )

    init_db()
    try:
        refresh_rates_if_stale()
    except Exception as e:
        app.logger.warning("Could not update exchange rates from NBRB: %s", e)

    from routes.analytics import bp as analytics_bp
    from routes.auth import bp as auth_bp
    from routes.balance import bp as balance_bp
    from routes.budget import bp as budget_bp
    from routes.dashboard import bp as dashboard_bp
    from routes.debts import bp as debts_bp
    from routes.history import bp as history_bp
    from routes.income import bp as income_bp
    from routes.savings import bp as savings_bp
    from routes.settings import bp as settings_bp

    @app.route("/favicon.ico")
    def favicon():
        return send_from_directory(
            os.path.join(app.root_path, "static"),
            "favicon.ico",
            mimetype="image/vnd.microsoft.icon",
        )

    for bp in (
        auth_bp,
        dashboard_bp,
        analytics_bp,
        income_bp,
        budget_bp,
        savings_bp,
        debts_bp,
        balance_bp,
        history_bp,
        settings_bp,
    ):
        app.register_blueprint(bp)

    @app.before_request
    def require_auth():
        if (
            request.path.startswith("/static/")
            or request.path == "/favicon.ico"
            or (request.endpoint and request.endpoint.startswith("auth."))
        ):
            return
        if not session.get("is_authenticated"):
            next_url = (
                request.full_path
                if request.method == "GET" and not request.path.startswith("/login")
                else None
            )
            return redirect(url_for("auth.login", next=next_url))


    @app.template_filter("to_byn")
    def to_byn_filter(amount, currency=BASE_CURRENCY):
        return "%.2f" % to_byn(amount, currency)

    @app.template_filter("to_usd")
    def to_usd_filter(amount, currency=BASE_CURRENCY):
        return "%.2f" % to_usd(amount, currency)

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
            "base_currency": BASE_CURRENCY,
            "currencies": CURRENCIES,
            "usd_rate": usd_rate(),
            "eur_rate": eur_rate(),
            "today": date.today(),
        }

    return app


app = create_app()

if __name__ == "__main__":
    import threading
    import webbrowser

    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0").lower() in ("1", "true", "yes")
    open_browser = os.environ.get("OPEN_BROWSER", "0").lower() in ("1", "true", "yes")
    url = os.environ.get("APP_URL", f"http://127.0.0.1:{port}/")

    if open_browser and (not debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true"):
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    app.run(host="127.0.0.1", port=port, debug=debug, use_reloader=debug)
