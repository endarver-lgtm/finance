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
    """Сумма в белорусских рублях по текущему курсу (для переоценки остатков на сегодня)."""
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
    """Перевод из BYN в указанную валюту по текущему курсу."""
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


def compute_entry_fx(
    amount: float,
    currency: str | None,
    amount_byn_custom: float | None = None,
) -> tuple[float, float, float, str]:
    """
    Вычисляет параметры валюты на момент операции: (rate_usd, rate_eur, amount_byn, fx_source).
    Если пользователь указал списанную банком сумму в BYN (amount_byn_custom), используется она.
    """
    amt = float(amount or 0)
    cur = normalize_currency(currency)
    r_usd = usd_rate()
    r_eur = eur_rate()

    if amount_byn_custom is not None and float(amount_byn_custom) > 0:
        return r_usd, r_eur, round(float(amount_byn_custom), 2), "custom"

    if cur == "BYN":
        byn = round(amt, 2)
    elif cur == "USD":
        byn = round(amt * r_usd, 2)
    elif cur == "EUR":
        byn = round(amt * r_eur, 2)
    else:
        byn = round(amt, 2)

    return r_usd, r_eur, byn, "entry"


def convert_at_entry(entry: dict, target_ccy: str) -> float:
    """
    Переводит запись из валюты записи в валюту цели по курсам этой записи (A1).
    Не подвержена изменению текущего курса в настройках.
    """
    target = normalize_currency(target_ccy)
    amt = float(entry.get("amount") or 0.0)
    cur = normalize_currency(entry.get("currency"))

    if cur == target:
        return round(amt, 2)

    # 1. Получаем сумму в BYN по историческому курсу операции
    if entry.get("amount_byn") is not None:
        byn = float(entry["amount_byn"])
    else:
        r_usd = float(entry.get("rate_usd") or usd_rate())
        r_eur = float(entry.get("rate_eur") or eur_rate())
        if cur == "BYN":
            byn = amt
        elif cur == "USD":
            byn = amt * r_usd
        elif cur == "EUR":
            byn = amt * r_eur
        else:
            byn = amt

    # 2. Переводим из BYN в target_ccy по историческому курсу операции
    r_usd = float(entry.get("rate_usd") or usd_rate())
    r_eur = float(entry.get("rate_eur") or eur_rate())

    if target == "BYN":
        return round(byn, 2)
    elif target == "USD":
        return round(byn / r_usd, 2) if r_usd > 0 else 0.0
    elif target == "EUR":
        return round(byn / r_eur, 2) if r_eur > 0 else 0.0

    return round(byn, 2)
