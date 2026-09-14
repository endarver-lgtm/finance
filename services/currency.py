from db.settings import get_setting
from services.constants import BASE_CURRENCY, CURRENCIES

DEFAULT_USD_RATE = 3.27
DEFAULT_EUR_RATE = 3.55


def normalize_currency(code: str | None) -> str:
    code = (code or BASE_CURRENCY).upper().strip()
    return code if code in CURRENCIES else BASE_CURRENCY


def usd_rate() -> float:
    return _rate("usd_rate", DEFAULT_USD_RATE)


def eur_rate() -> float:
    return _rate("eur_rate", DEFAULT_EUR_RATE)


def _rate(key: str, default: float) -> float:
    try:
        value = float(get_setting(key, str(default)))
        return value if value > 0 else default
    except (TypeError, ValueError):
        return default


def to_byn(amount: float, currency: str | None) -> float:
    """Сумма в белорусских рублях (для сводок и KPI)."""
    amount = float(amount or 0)
    currency = normalize_currency(currency)
    if currency == "BYN":
        return round(amount, 2)
    if currency == "USD":
        return round(amount * usd_rate(), 2)
    if currency == "EUR":
        return round(amount * eur_rate(), 2)
    return round(amount, 2)


def from_byn(byn: float, currency: str | None) -> float:
    """Перевод из BYN в указанную валюту."""
    byn = float(byn or 0)
    currency = normalize_currency(currency)
    if currency == "BYN":
        return round(byn, 2)
    if currency == "USD":
        return round(byn / usd_rate(), 2)
    if currency == "EUR":
        return round(byn / eur_rate(), 2)
    return round(byn, 2)


def to_usd(amount: float, currency: str | None) -> float:
    currency = normalize_currency(currency)
    return round(to_byn(amount, currency) / usd_rate(), 2)


def convert(amount: float, from_currency: str | None, to_currency: str | None) -> float:
    return from_byn(to_byn(amount, from_currency), to_currency)
