def usage_percent(spent: float, planned: float) -> float:
    if planned <= 0:
        return 0.0
    return min(100.0, round(spent / planned * 100, 1))


def progress_color(pct: float) -> str:
    if pct >= 90:
        return "danger"
    if pct >= 70:
        return "warning"
    return "ok"


def income_status(fact: float, planned: float) -> str:
    if fact > 0 and planned <= 0:
        return "received"
    if planned > 0 and fact >= planned:
        return "received"
    if fact > 0:
        return "partial"
    return "pending"
