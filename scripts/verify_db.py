"""Проверка сохранения данных после reset. Запуск: python scripts/verify_db.py"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from datetime import date

from db import get_db, init_db, reset_db
from services.currency import to_byn
from services.repository import (
    create_budget_category,
    create_budget_entry,
    create_income_entry,
    create_income_source,
    create_savings_entry,
    create_savings_goal,
)
from db.settings import get_setting, set_setting


def check(label: str, ok: bool, detail: str = ""):
    status = "OK" if ok else "FAIL"
    msg = f"  [{status}] {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    return ok


def main():
    print("=== Сброс БД ===")
    reset_db()
    init_db()

    today = date.today().isoformat()

    print("\n=== Запись тестовых данных ===")
    create_income_source("Зарплата", "regular", 3000, "monthly", "USD")
    create_income_source("Фриланс", "regular", 500, "monthly", "EUR")
    create_income_entry(1, 2800, today, "аванс", "USD")
    create_income_entry(2, 500, today, None, "EUR")
    create_income_entry(None, 100, today, "разовый", "BYN")

    create_budget_category("Продукты", 400, "week", "BYN")
    create_budget_category("Подписки", 15, "month", "USD")
    create_budget_entry(1, 120, today, "магазин", "BYN")
    create_budget_entry(2, 10, today, "spotify", "USD")

    create_savings_goal("Отпуск", "want", 5000, "2026-12-31", "EUR")
    create_savings_goal("Резерв", "reserve", 1000, None, "BYN")
    create_savings_entry(1, 200, today, "старт", "USD")
    create_savings_entry(2, 300, today, None, "BYN")

    set_setting("usd_rate", "3.30")
    set_setting("eur_rate", "3.60")

    print("\n=== Проверка таблиц ===")
    all_ok = True

    with get_db() as conn:
        sources = conn.execute("SELECT * FROM income_sources ORDER BY id").fetchall()
        all_ok &= check("income_sources", len(sources) == 2, f"rows={len(sources)}")
        s1 = dict(sources[0])
        all_ok &= check(
            "income_sources.currency",
            s1["name"] == "Зарплата" and s1["currency"] == "USD" and s1["planned_amount"] == 3000,
            str(dict(s1)),
        )

        entries = conn.execute("SELECT * FROM income_entries ORDER BY id").fetchall()
        all_ok &= check("income_entries", len(entries) == 3, f"rows={len(entries)}")
        e3 = dict(entries[2])
        all_ok &= check(
            "income_entries one-time",
            e3["source_id"] is None and e3["currency"] == "BYN" and e3["amount"] == 100,
            str(e3),
        )

        cats = conn.execute("SELECT * FROM budget_categories ORDER BY id").fetchall()
        all_ok &= check("budget_categories", len(cats) == 2)
        all_ok &= check(
            "budget_categories.currency",
            dict(cats[1])["currency"] == "USD",
        )

        be = conn.execute("SELECT * FROM budget_entries ORDER BY id").fetchall()
        all_ok &= check("budget_entries", len(be) == 2)
        all_ok &= check(
            "budget_entries.currency",
            dict(be[1])["currency"] == "USD" and dict(be[1])["amount"] == 10,
        )

        goals = conn.execute("SELECT * FROM savings_goals ORDER BY id").fetchall()
        all_ok &= check("savings_goals", len(goals) == 2)
        all_ok &= check(
            "savings_goals.currency",
            dict(goals[0])["currency"] == "EUR" and dict(goals[0])["target_amount"] == 5000,
        )

        se = conn.execute("SELECT * FROM savings_entries ORDER BY id").fetchall()
        all_ok &= check("savings_entries", len(se) == 2)
        all_ok &= check(
            "savings_entries.currency",
            dict(se[0])["currency"] == "USD",
        )

        settings = {
            r["key"]: r["value"]
            for r in conn.execute("SELECT key, value FROM settings").fetchall()
        }
        all_ok &= check("settings", settings.get("currency") == "BYN")
        all_ok &= check("settings.usd_rate", settings.get("usd_rate") == "3.30")
        all_ok &= check("settings.eur_rate", settings.get("eur_rate") == "3.60")

    print("\n=== Проверка конвертации (сводка BYN) ===")
    with get_db() as conn:
        inc = conn.execute("SELECT amount, currency FROM income_entries").fetchall()
    total_byn = sum(to_byn(r["amount"], r["currency"]) for r in inc)
    # 2800 USD * 3.3 + 500 EUR * 3.6 + 100 BYN
    expected = round(2800 * 3.3 + 500 * 3.6 + 100, 2)
    all_ok &= check(
        "income BYN total",
        abs(total_byn - expected) < 0.01,
        f"got {total_byn}, expected {expected}",
    )

    print("\n=== HTTP smoke ===")
    from app import app

    client = app.test_client()
    all_ok &= check("GET /", client.get("/").status_code == 200)
    all_ok &= check("GET /income", client.get("/income/").status_code == 200)
    all_ok &= check("GET /budget", client.get("/budget/").status_code == 200)
    all_ok &= check("GET /savings", client.get("/savings/").status_code == 200)
    all_ok &= check("GET /history", client.get("/history/").status_code == 200)

    r = client.post(
        "/income/one-time/add",
        data={"amount": "50", "currency": "USD", "date": today, "comment": "http"},
    )
    all_ok &= check("POST income one-time", r.status_code in (302, 200))
    with get_db() as conn:
        last = conn.execute(
            "SELECT amount, currency, comment FROM income_entries ORDER BY id DESC LIMIT 1"
        ).fetchone()
    all_ok &= check(
        "POST saved to DB",
        last and last["amount"] == 50 and last["currency"] == "USD" and last["comment"] == "http",
        str(dict(last)) if last else "no row",
    )

    print("\n" + ("=== ВСЁ OK ===" if all_ok else "=== ЕСТЬ ОШИБКИ ==="))
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
