from datetime import date
from typing import Optional

from services.constants import ENVELOPE_PCT_THRESHOLDS, TEMPO_RATIO_THRESHOLDS
from services.dates import parse_date


def usage_percent(spent: float, planned: float, clamp: bool = False) -> float:
    """
    Процент использования лимита (E1).
    По умолчанию clamp=False (честная полоска без обрезания на 100%).
    """
    if planned <= 0:
        return 0.0
    val = round(spent / planned * 100, 1)
    return min(100.0, val) if clamp else val


def progress_color(pct: float) -> str:
    """
    Пороги цвета полоски лимита (E1):
    < 80% — ok (зеленый)
    80..<100% — warning (желтый)
    >= 100% — danger (красный)
    """
    if pct >= ENVELOPE_PCT_THRESHOLDS["warning"]:
        return "danger"
    if pct >= ENVELOPE_PCT_THRESHOLDS["ok"]:
        return "warning"
    return "ok"


def envelope_tempo(
    spent: float,
    limit: float,
    start_date: date,
    end_date: date,
    ref_date: Optional[date] = None,
) -> Optional[dict]:
    """
    Вычисляет темп расходования по конверту (E2):
    - Для конвертов с лимитом > 0
    - Со 2-го дня периода (в 1-й день возвращает None)
    - elapsed = прошло дней / дней в периоде
    - ratio = (pct / 100) / elapsed
    """
    if limit <= 0.005:
        return None

    ref = ref_date or date.today()
    total_days = max(1, (end_date - start_date).days + 1)
    passed_days = (ref - start_date).days + 1

    # В 1-й день темп не рассчитывается
    if passed_days < 2:
        return None

    passed_clamped = min(total_days, max(1, passed_days))
    elapsed = passed_clamped / total_days

    pct = (spent / limit) * 100
    ratio = round((pct / 100.0) / elapsed, 2) if elapsed > 0 else 1.0

    days_remaining = max(1, (end_date - ref).days + 1)
    remaining_limit = limit - spent
    safe_daily = round(remaining_limit / days_remaining, 2)

    # Статус темпа
    if ratio <= TEMPO_RATIO_THRESHOLDS["ok"]:
        status = "ok"
        msg = f"В графике (расход на {round((1.0 - ratio)*100)}% ниже нормы)"
    elif ratio <= TEMPO_RATIO_THRESHOLDS["warning"]:
        status = "warning"
        msg = f"Опережаете график на {round((ratio - 1.0)*100)}%"
    else:
        status = "danger"
        msg = f"Опережаете график на {round((ratio - 1.0)*100)}%"

    return {
        "ratio": ratio,
        "status": status,
        "message": msg,
        "safe_daily": safe_daily,
        "days_remaining": days_remaining,
    }


def income_status(
    fact: float,
    planned: float,
    expected_date: Optional[str] = None,
    ref_date: Optional[date] = None,
) -> str:
    """
    Статусы приходов (D2):
    - received: факт >= план
    - partial: 0 < факт < план
    - overdue: ожидаемая дата прошла, а доход не поступил
    - pending: в ожидании
    """
    ref = ref_date or date.today()
    if fact >= planned - 0.005 and (planned > 0 or fact > 0):
        return "received"
    if fact > 0.005:
        return "partial"
    if expected_date:
        exp_d = parse_date(expected_date)
        if exp_d and exp_d < ref:
            return "overdue"
    return "pending"
