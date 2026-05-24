from datetime import date

from flask import request

from services.dates import parse_date, to_iso


def parse_period_arg(
    allowed: dict[str, str], default: str, arg: str = "period"
) -> str:
    period = request.args.get(arg, default)
    return period if period in allowed else default


def parse_money(name: str = "amount") -> float:
    return float(request.form.get(name) or 0)


def parse_entry_fields() -> tuple[float, str, str | None]:
    amount = parse_money()
    entry_date = to_iso(
        parse_date(request.form.get("date") or date.today().isoformat())
    )
    comment = request.form.get("comment", "").strip() or None
    return amount, entry_date, comment
