import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta

from db.settings import get_setting, set_setting

NBRB_API_BASE = "https://api.nbrb.by/exrates/rates"
RATE_REFRESH_INTERVAL = timedelta(days=1)


def rates_are_stale(now: datetime | None = None) -> bool:
    updated_at = get_setting("rates_updated_at", "")
    try:
        updated_at = datetime.strptime(updated_at, "%d.%m.%Y %H:%M")
    except (TypeError, ValueError):
        return True
    return (now or datetime.now()) - updated_at >= RATE_REFRESH_INTERVAL


def fetch_nbrb_rate(cur_code: str, ondate: str | None = None) -> dict:
    """Получает курс валюты с официального API НБРБ.
    
    https://www.nbrb.by/apihelp/exrates
    """
    url = f"{NBRB_API_BASE}/{cur_code.upper()}?parammode=2"
    if ondate:
        url += f"&ondate={ondate}"

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "FinanceTracker/1.0 (Windows NT 10.0; Win64; x64)"},
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Ошибка API НБРБ ({e.code}): {e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Не удалось подключиться к API НБРБ: {e.reason}. Проверьте интернет-соединение."
        ) from e
    except TimeoutError as e:
        raise RuntimeError("Время ожидания ответа от API НБРБ истекло.") from e
    except Exception as e:
        raise RuntimeError(f"Ошибка при получении курса {cur_code}: {e}") from e

    scale = float(data.get("Cur_Scale", 1))
    rate = round(float(data["Cur_OfficialRate"]) / scale, 4)
    rate_date = data.get("Date", "").split("T")[0]

    return {
        "code": cur_code.upper(),
        "name": data.get("Cur_Name", ""),
        "scale": int(scale),
        "official_rate": float(data["Cur_OfficialRate"]),
        "rate": rate,
        "date": rate_date,
    }


def fetch_all_rates(currencies=("USD", "EUR"), ondate: str | None = None) -> dict:
    """Получает курсы для списка валют (по умолчанию USD и EUR)."""
    results = {}
    dates = set()
    for cur in currencies:
        info = fetch_nbrb_rate(cur, ondate=ondate)
        results[cur] = info["rate"]
        if info.get("date"):
            dates.add(info["date"])

    results["date"] = sorted(dates)[-1] if dates else datetime.now().strftime("%Y-%m-%d")
    return results


def refresh_rates_if_stale() -> dict | None:
    if not rates_are_stale():
        return None
    return sync_rates_from_nbrb()


def sync_rates_from_nbrb(ondate: str | None = None) -> dict:
    """Получает актуальные курсы с НБРБ и сохраняет их в базу данных."""
    rates = fetch_all_rates(currencies=("USD", "EUR"), ondate=ondate)

    set_setting("usd_rate", str(rates["USD"]))
    set_setting("eur_rate", str(rates["EUR"]))

    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    set_setting("rates_updated_at", now_str)
    set_setting("rates_nbrb_date", rates.get("date", ""))

    return {
        "usd_rate": rates["USD"],
        "eur_rate": rates["EUR"],
        "nbrb_date": rates.get("date", ""),
        "updated_at": now_str,
    }
