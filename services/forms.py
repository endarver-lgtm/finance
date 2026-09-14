from datetime import date

from flask import request

from services.currency import normalize_currency
from services.dates import parse_date, to_iso


def parse_period_arg(
    allowed: dict[str, str], default: str, arg: str = "period"
) -> str:
    period = request.args.get(arg, default)
    return period if period in allowed else default


def parse_money(name: str = "amount") -> float:
    return float(request.form.get(name) or 0)


def parse_currency(name: str = "currency") -> str:
    return normalize_currency(request.form.get(name))


def parse_entry_fields() -> tuple[float, str, str | None, str]:
    return (
        parse_money(),
        to_iso(parse_date(request.form.get("date") or date.today().isoformat())),
        request.form.get("comment", "").strip() or None,
        parse_currency(),
    )
