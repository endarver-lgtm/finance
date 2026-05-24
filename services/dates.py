from datetime import date, datetime, timedelta
from calendar import monthrange


def parse_date(s: str) -> date:
    if isinstance(s, date):
        return s
    if "T" in s:
        s = s.split("T")[0]
    parts = s.split("-")
    if len(parts) == 3 and len(parts[0]) == 4:
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    parts = s.split(".")
    return date(int(parts[2]), int(parts[1]), int(parts[0]))


def format_date(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def to_iso(d: date) -> str:
    return d.isoformat()


def period_bounds(period: str, ref: date | None = None) -> tuple[date, date]:
    ref = ref or date.today()
    if period == "day":
        return ref, ref
    if period == "week":
        start = ref - timedelta(days=ref.weekday())
        end = start + timedelta(days=6)
        return start, end
    if period == "month":
        start = ref.replace(day=1)
        last = monthrange(ref.year, ref.month)[1]
        end = ref.replace(day=last)
        return start, end
    if period == "year":
        return date(ref.year, 1, 1), date(ref.year, 12, 31)
    start = ref.replace(day=1)
    last = monthrange(ref.year, ref.month)[1]
    return start, ref.replace(day=last)


def month_start(d: date) -> date:
    return d.replace(day=1)


def add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    day = min(d.day, monthrange(y, m)[1])
    return date(y, m, day)


def last_n_months(n: int, ref: date | None = None) -> list[tuple[date, date]]:
    ref = ref or date.today()
    end_month = month_start(ref)
    months = []
    for i in range(n - 1, -1, -1):
        m_start = add_months(end_month, -i)
        last = monthrange(m_start.year, m_start.month)[1]
        m_end = date(m_start.year, m_start.month, last)
        months.append((m_start, m_end))
    return months


def month_label(d: date) -> str:
    months = [
        "Янв", "Фев", "Мар", "Апр", "Май", "Июн",
        "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек",
    ]
    return f"{months[d.month - 1]} {d.year}"
