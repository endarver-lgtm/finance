import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE_PATH = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "finance.db"))
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-change-me-in-production")
DEFAULT_CURRENCY = "€"
