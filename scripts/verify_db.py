import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
test_db = str(ROOT / "test_verify.db")
os.environ["DATABASE_PATH"] = test_db

from datetime import date, timedelta

from db import get_db, init_db, reset_db
from db.migrate import migrate_db
from db.settings import get_setting, set_setting
from services.analytics import (
    budget_fact_from_goals,
    budget_fact_own,
    envelope_progress,
    free_cash_flow,
    income_fact,
    savings_total,
)
from services.currency import to_byn
from services.debts import (
    add_debt_entry,
    add_split,
    balance_total,
    debt_balance,
    delete_debt,
    delta_b,
)
from services.reconcile import calculate_expected, get_last_check, save_check
from services.repository import (
    create_budget_category,
    create_budget_entry,
    create_income_entry,
    create_income_source,
    create_savings_entry,
    create_savings_goal,
)
from services.savings import (
    delete_savings_entry,
    goal_balance,
    withdraw_from_goal,
)


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
    all_ok = True

    print("\n=== Базовые проверки таблиц и схемы ===")
    create_income_source("Зарплата", "regular", 3000, "monthly", "USD")
    create_income_source("Фриланс", "regular", 500, "monthly", "EUR")
    create_income_entry(1, 2800, today, "аванс", "USD")
    create_income_entry(2, 500, today, None, "EUR")
    create_income_entry(None, 100, today, "разовый", "BYN")

    create_budget_category("Продукты", 400, "week", "BYN")
    create_budget_category("Подписки", 15, "month", "USD")
    create_budget_entry(2, 120, today, "магазин", "BYN")
    create_budget_entry(3, 10, today, "spotify", "USD")

    create_savings_goal("Отпуск", "want", 5000, "2026-12-31", "EUR")
    create_savings_goal("Резерв", "reserve", 1000, None, "BYN")
    create_savings_entry(1, 200, today, "старт", "USD")
    create_savings_entry(2, 300, today, None, "BYN")

    set_setting("usd_rate", "3.30")
    set_setting("eur_rate", "3.60")

    with get_db() as conn:
        sources = conn.execute("SELECT * FROM income_sources ORDER BY id").fetchall()
        all_ok &= check("income_sources", len(sources) == 2, f"rows={len(sources)}")

        cats = conn.execute("SELECT * FROM budget_categories ORDER BY id").fetchall()
        # 1: Неучтёнка, 2: Продукты, 3: Подписки
        all_ok &= check("budget_categories count", len(cats) == 3, f"rows={len(cats)}")
        all_ok &= check("system category exists", any(c["name"] == "Неучтёнка" and c["is_system"] == 1 for c in cats))

        be = conn.execute("SELECT * FROM budget_entries ORDER BY id").fetchall()
        all_ok &= check("budget_entries", len(be) == 2)

        goals = conn.execute("SELECT * FROM savings_goals ORDER BY id").fetchall()
        all_ok &= check("savings_goals", len(goals) == 2)

        se = conn.execute("SELECT * FROM savings_entries ORDER BY id").fetchall()
        all_ok &= check("savings_entries kind default", all(s["kind"] == "deposit" for s in se))

        settings = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings").fetchall()}
        all_ok &= check("settings defaults", settings.get("savings_in_check") == "1" and settings.get("default_debt_person") == "Кент")

    print("\n=== HTTP Smoke ===")
    from app import app
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["is_authenticated"] = True
    all_ok &= check("GET /", client.get("/").status_code == 200)
    all_ok &= check("GET /analytics", client.get("/analytics/").status_code == 200)
    all_ok &= check("GET /income", client.get("/income/").status_code == 200)
    all_ok &= check("GET /budget", client.get("/budget/").status_code == 200)
    all_ok &= check("GET /savings", client.get("/savings/").status_code == 200)
    all_ok &= check("GET /debts", client.get("/debts/").status_code == 200)
    all_ok &= check("GET /balance", client.get("/balance/").status_code == 200)
    all_ok &= check("GET /history", client.get("/history/").status_code == 200)

    # -------------------------------------------------------------
    # ТЕСТЫ ИЗ РАЗДЕЛА 8 ТЗ (Курсы USD/EUR = 3.0 для простоты)
    # -------------------------------------------------------------
    print("\n=== Тесты по разделу 8 ТЗ ===")
    reset_db()
    init_db()
    set_setting("usd_rate", "3.0")
    set_setting("eur_rate", "3.0")

    today_d = date.today()
    day_start = today_d
    day_end = today_d

    # A. Снятие с тратой
    # Цель «Ноутбук» с взносами 500. Снять 200, purpose = spent, категория «Развлечения».
    create_budget_category("Развлечения", 500, "month", "BYN")  # cat id 2 (id 1 is Неучтёнка)
    create_savings_goal("Ноутбук", "want", 2000, None, "BYN")   # goal id 1
    create_savings_entry(1, 500, today, "стартовый взнос", "BYN")

    cat_razv = 2
    goal_laptop = 1

    free_before_a = free_cash_flow(day_start, day_end)
    own_exp_before_a = budget_fact_own(day_start, day_end)

    res_a = withdraw_from_goal(
        goal_id=goal_laptop,
        amount=200,
        currency="BYN",
        entry_date=today,
        purpose="spent",
        category_id=cat_razv,
        comment="покупка части ноута",
    )

    bal_laptop_a = goal_balance(goal_laptop)
    own_exp_after_a = budget_fact_own(day_start, day_end)
    goals_exp_a = budget_fact_from_goals(day_start, day_end)
    free_after_a = free_cash_flow(day_start, day_end)

    # Проверка процента конверта
    env_razv = next((e for e in envelope_progress("month", today_d) if e["id"] == cat_razv), None)
    pct_razv = env_razv["pct"] if env_razv else 0

    all_ok &= check("A. Накоплено по цели 300", abs(bal_laptop_a - 300) < 0.005, f"got {bal_laptop_a}")
    all_ok &= check("A. Расход 200 из копилки", goals_exp_a == 200, f"got {goals_exp_a}")
    all_ok &= check("A. Собственные расходы не изменились", own_exp_after_a == own_exp_before_a)
    all_ok &= check("A. Процент конверта не изменился (0%)", pct_razv == 0, f"got {pct_razv}")
    all_ok &= check("A. Free не изменился", free_after_a == free_before_a, f"before={free_before_a}, after={free_after_a}")

    # B. Снятие в свободные. Снять 100, purpose = free.
    free_before_b = free_cash_flow(day_start, day_end)
    res_b = withdraw_from_goal(
        goal_id=goal_laptop,
        amount=100,
        currency="BYN",
        entry_date=today,
        purpose="free",
        comment="вернул в свободные",
    )
    bal_laptop_b = goal_balance(goal_laptop)
    free_after_b = free_cash_flow(day_start, day_end)

    all_ok &= check("B. Накоплено по цели 200", abs(bal_laptop_b - 200) < 0.005, f"got {bal_laptop_b}")
    all_ok &= check("B. Free +100", abs(free_after_b - (free_before_b + 100)) < 0.005, f"before={free_before_b}, after={free_after_b}")

    # C. Превышение. Снять 1000 при накопленных 200 -> ошибка, в БД ничего не добавилось.
    c_failed = False
    try:
        withdraw_from_goal(goal_laptop, 1000, "BYN", today, "free")
    except ValueError:
        c_failed = True

    bal_laptop_c = goal_balance(goal_laptop)
    all_ok &= check("C. Превышение вызывает ошибку", c_failed and abs(bal_laptop_c - 200) < 0.005)

    # D. Раздел, платил я. Трата 60, моя доля 30 (кент 30), категория «Еда».
    create_budget_category("Еда", 400, "week", "BYN")  # cat id 3
    cat_eda = 3

    free_before_d = free_cash_flow(day_start, day_end)
    res_d = add_split(
        total_amount=60,
        currency="BYN",
        entry_date=today,
        paid_by="me",
        person="Кент",
        my_share=30,
        category_id=cat_eda,
        comment="обед в кафе",
    )
    b_d = debt_balance("Кент")
    free_after_d = free_cash_flow(day_start, day_end)

    with get_db() as conn:
        be_eda = conn.execute("SELECT amount FROM budget_entries WHERE id = ?", (res_d["budget_entry_id"],)).fetchone()

    all_ok &= check("D. Расход 30 в Еда", be_eda and be_eda["amount"] == 30)
    all_ok &= check("D. B = +30 (Кент должен)", abs(b_d - 30) < 0.005, f"got {b_d}")
    all_ok &= check("D. Free -60", abs(free_after_d - (free_before_d - 60)) < 0.005, f"diff={free_after_d - free_before_d}")

    # E. Раздел, платил он. Трата 50, моя доля 20.
    free_before_e = free_cash_flow(day_start, day_end)
    res_e = add_split(
        total_amount=50,
        currency="BYN",
        entry_date=today,
        paid_by="him",
        person="Кент",
        my_share=20,
        category_id=cat_eda,
        comment="ужин",
    )
    b_e = debt_balance("Кент")
    free_after_e = free_cash_flow(day_start, day_end)

    all_ok &= check("E. B стал +10 (+30 - 20)", abs(b_e - 10) < 0.005, f"got {b_e}")
    all_ok &= check("E. Free не изменился от этой операции", abs(free_after_e - free_before_e) < 0.005, f"diff={free_after_e - free_before_e}")

    # F. Возврат. repay_from_him 10 -> B = 0; Free +10; приходов не прибавилось.
    free_before_f = free_cash_flow(day_start, day_end)
    inc_before_f = income_fact(day_start, day_end)
    add_debt_entry(person="Кент", kind="repay_from_him", amount=10, currency="BYN", entry_date=today, comment="отдал долг")
    b_f = debt_balance("Кент")
    free_after_f = free_cash_flow(day_start, day_end)
    inc_after_f = income_fact(day_start, day_end)

    all_ok &= check("F. B = 0", abs(b_f) < 0.005, f"got {b_f}")
    all_ok &= check("F. Free +10", abs(free_after_f - (free_before_f + 10)) < 0.005, f"diff={free_after_f - free_before_f}")
    all_ok &= check("F. Приходов не прибавилось", inc_after_f == inc_before_f)

    # G. Доля 0. Трата 40, платил я, моя доля 0 -> расхода в конверт нет; i_paid 40.
    with get_db() as conn:
        be_count_before_g = conn.execute("SELECT count(*) as c FROM budget_entries").fetchone()["c"]

    res_g = add_split(
        total_amount=40,
        currency="BYN",
        entry_date=today,
        paid_by="me",
        person="Кент",
        my_share=0,
        category_id=None,
        comment="купил ему лекарства",
    )

    with get_db() as conn:
        be_count_after_g = conn.execute("SELECT count(*) as c FROM budget_entries").fetchone()["c"]

    all_ok &= check("G. Расхода в конверт нет", be_count_after_g == be_count_before_g and res_g["budget_entry_id"] is None)
    all_ok &= check("G. i_paid 40 записан (B=+40)", abs(debt_balance("Кент") - 40) < 0.005)

    # H. Удаление.
    # Удалить запись из D -> связанный расход тоже удалён, B пересчитан.
    with get_db() as conn:
        debt_d = conn.execute("SELECT id FROM debts WHERE budget_entry_id = ?", (res_d["budget_entry_id"],)).fetchone()
    if debt_d:
        delete_debt(debt_d["id"])
        with get_db() as conn:
            be_d_check = conn.execute("SELECT id FROM budget_entries WHERE id = ?", (res_d["budget_entry_id"],)).fetchone()
        all_ok &= check("H. Связанный расход D удалён", be_d_check is None)
        # Был +40, без D (i_paid 30) стало 40 - 30 = 10
        all_ok &= check("H. B пересчитан (10)", abs(debt_balance("Кент") - 10) < 0.005, f"got {debt_balance('Кент')}")

    # Удалить снятие из A -> связанный расход удалён, накоплено по цели 500
    delete_savings_entry(res_a["savings_entry_id"])
    with get_db() as conn:
        be_a_check = conn.execute("SELECT id FROM budget_entries WHERE id = ?", (res_a["budget_entry_id"],)).fetchone()
    all_ok &= check("H. Связанный расход A удалён", be_a_check is None)
    # Было 200, вернули 200 -> стало 400 (плюс снятие в свободные 100 оставалось). Удалим и B:
    delete_savings_entry(res_b["savings_entry_id"])
    bal_laptop_h = goal_balance(goal_laptop)
    all_ok &= check("H. Накоплено по цели 500", abs(bal_laptop_h - 500) < 0.005, f"got {bal_laptop_h}")

    # I. Сверка.
    print("\n--- Тест I: Сверка ---")
    reset_db()
    init_db()
    set_setting("usd_rate", "3.0")
    set_setting("eur_rate", "3.0")
    set_setting("savings_in_check", "1")

    # Базовая дата вчера, чтобы операции сегодня были date > last_check.date
    yesterday_str = (date.today() - timedelta(days=1)).isoformat()
    today_str = date.today().isoformat()

    # 1. Первая сверка: на руках 1000 -> базовая точка, diff = NULL.
    chk1 = save_check({"byn": 1000}, check_date=yesterday_str)
    all_ok &= check("I.1 Первая сверка real=1000, diff=None", chk1["real_byn"] == 1000 and chk1["diff_byn"] is None)

    # 2. После неё: приход 300, собственный расход 80, раздел «платил я» (всего 60, моя доля 30).
    create_income_entry(None, 300, today_str, "приход", "BYN")
    create_budget_category("Кафе", 200, "month", "BYN")
    create_budget_entry(2, 80, today_str, "собственный", "BYN")
    add_split(total_amount=60, currency="BYN", entry_date=today_str, paid_by="me", person="Кент", my_share=30, category_id=2)

    # 3. Ожидается expected = 1000 + 300 − 80 − 30 − 30 = 1160 при savings_in_check = 1.
    calc_i = calculate_expected(1150, today_str)
    all_ok &= check("I.3 expected = 1160", calc_i["expected_byn"] == 1160, f"got {calc_i['expected_byn']}")

    # 4. Ввести реально 1150 -> diff = −10; при resolution = expense создан расход 10 в «Неучтёнка» датой сверки.
    chk2 = save_check({"byn": 1150}, check_date=today_str, resolution="expense")
    all_ok &= check("I.4 diff = -10", chk2["diff_byn"] == -10, f"got {chk2['diff_byn']}")
    all_ok &= check("I.4 adjust_expense создан", chk2["adjust_expense_id"] is not None)

    with get_db() as conn:
        adj = conn.execute("SELECT c.name, b.amount, b.date FROM budget_entries b JOIN budget_categories c ON c.id = b.category_id WHERE b.id = ?", (chk2["adjust_expense_id"],)).fetchone()
    all_ok &= check("I.4 списано 10 в Неучтёнка", adj and adj["name"] == "Неучтёнка" and adj["amount"] == 10 and adj["date"] == today_str)

    # 5. Следующая сверка без новых операций с реальным 1150 -> diff = 0
    calc_i5 = calculate_expected(1150, today_str)
    all_ok &= check("I.5 diff = 0 при повторной сверке 1150", calc_i5["diff_byn"] == 0, f"got {calc_i5['diff_byn']}")

    # J. Системная категория.
    print("\n--- Тест J: Системная категория ---")
    with get_db() as conn:
        neuch = conn.execute("SELECT * FROM budget_categories WHERE name = 'Неучтёнка'").fetchone()
    all_ok &= check("J. Неучтёнка is_system=1 and track_only=1", neuch and neuch["is_system"] == 1 and neuch["track_only"] == 1)

    # K. Миграции.
    print("\n--- Тест K: Миграции ---")
    with get_db() as conn:
        migrate_db(conn)
    all_ok &= check("K. Повторный запуск migrate_db ничего не ломает", True)

    print("\n" + ("=== ВСЕ ПРОВЕРКИ И ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО (OK) ===" if all_ok else "=== ЕСТЬ ОШИБКИ ==="))
    if os.path.exists(test_db):
        try:
            os.remove(test_db)
        except Exception:
            pass
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
