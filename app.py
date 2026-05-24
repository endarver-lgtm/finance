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

    @app.context_processor
    def inject_globals():
        return {
            "currency": get_setting("currency", DEFAULT_CURRENCY),
            "today": date.today(),
        }

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
