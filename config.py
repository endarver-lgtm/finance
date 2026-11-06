import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_dotenv():
    env_path = os.path.join(BASE_DIR, ".env")
    if not os.path.isfile(env_path):
        return
    with open(env_path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


_load_dotenv()

DATABASE_PATH = os.environ.get(
    "DATABASE_PATH", os.path.join(BASE_DIR, "finance.db")
)
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-change-me-in-production")
APP_PASSWORD = os.environ.get("APP_PASSWORD") or os.environ.get("APP_PIN") or "9002"
# Backward-compatibility alias
APP_PIN = APP_PASSWORD
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
DEFAULT_CURRENCY = os.environ.get("DEFAULT_CURRENCY", "BYN")
DEFAULT_USD_RATE = os.environ.get("USD_RATE", "3.27")
DEFAULT_EUR_RATE = os.environ.get("EUR_RATE", "3.55")
