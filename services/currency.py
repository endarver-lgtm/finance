from db.settings import get_setting

DEFAULT_USD_RATE = 3.27


def usd_rate() -> float:
    raw = get_setting("usd_rate", str(DEFAULT_USD_RATE))
    try:
        rate = float(raw)
        return rate if rate > 0 else DEFAULT_USD_RATE
    except (TypeError, ValueError):
        return DEFAULT_USD_RATE


def to_usd(byn: float, rate: float | None = None) -> float:
    rate = rate or usd_rate()
    return round(float(byn) / rate, 2)
