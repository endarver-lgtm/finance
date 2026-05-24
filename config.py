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

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-change-me-in-production")
DEFAULT_CURRENCY = os.environ.get("DEFAULT_CURRENCY", "€")
