import os
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
test_db = str(ROOT / "test_verify.db")
os.environ["DATABASE_PATH"] = test_db

from db import get_db, init_db, reset_db
from db.settings import get_setting, set_setting
from services.analytics import (
    calculate_accounting_accuracy,
    calculate_budget_adherence,
    calculate_daily_burn_and_forecast,
    cash_flow_waterfall,
    category_comparison_and_pareto,
    goals_analytics,
    health_metrics,
    six_months_trends,
)
from services.constants import (
    ADHERENCE_THRESHOLDS,
    RUNWAY_THRESHOLDS,
    SAVINGS_RATE_THRESHOLDS,
    TEMPO_RATIO_THRESHOLDS,
)
from services.currency import usd_rate
from services.dates import period_bounds
from services.debts import add_debt_entry, add_split
from services.metrics_core import (
    PeriodMetrics,
    get_period_metrics,
    history_months,
)
from services.planning import scale_plan
from services.progress import envelope_tempo, usage_percent
from services.reconcile import calculate_expected, save_check
from services.repository import (
    create_budget_category,
    create_budget_entry,
    create_income_entry,
    create_income_source,
    create_savings_entry,
    create_savings_goal,
)
from services.savings import goal_balance, withdraw_from_goal


def check(label: str, ok: bool, detail: str = ""):
    status = "OK" if ok else "FAIL"
    msg = f"  [{status}] {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    if not ok:
        raise AssertionError(f"Test failed: {label} — {detail}")
    return ok


def run_tests():
    print("\n=== Запуск аналитических тестов H-1 ... H-17 ===")

    # -------------------------------------------------------------
    # H-14: scale_plan validation
    # -------------------------------------------------------------
    # недельный 100 в 30-дневном месяце = 428,57
    sp1 = scale_plan(100.0, "week", date(2026, 4, 1), date(2026, 4, 30))
    check("H-14.1 scale_plan week in 30d month == 428.57", abs(sp1 - 428.57) < 0.01, f"got {sp1}")

    # месячный 400 в неделе = 92,05
    sp2 = scale_plan(400.0, "month", date(2026, 5, 4), date(2026, 5, 10))
    check("H-14.2 scale_plan month in 7d week == 92.05", abs(sp2 - 92.05) < 0.01, f"got {sp2}")

    # недельный 100 за год = 5214,29
    sp3 = scale_plan(100.0, "week", date(2026, 1, 1), date(2026, 12, 31))
    check("H-14.3 scale_plan week in year == 5214.29", abs(sp3 - 5214.29) < 0.02, f"got {sp3}")

    # месячный 400 за год = 4800
    sp4 = scale_plan(400.0, "month", date(2026, 1, 1), date(2026, 12, 31))
    check("H-14.4 scale_plan month in year == 4800.0", abs(sp4 - 4800.0) < 0.01, f"got {sp4}")

    # месячный 400 в месяце = 400
    sp5 = scale_plan(400.0, "month", date(2026, 4, 1), date(2026, 4, 30))
    check("H-14.5 scale_plan month in month == 400.0", abs(sp5 - 400.0) < 0.01, f"got {sp5}")

    # -------------------------------------------------------------
    # H-15: Progress & Tempo validation
    # -------------------------------------------------------------
    pct_150 = usage_percent(150.0, 100.0)
    rem_150 = 100.0 - 150.0
    check("H-15.1 Overrun 150% -> pct=150", abs(pct_150 - 150.0) < 0.01, f"got {pct_150}")
    check("H-15.2 Overrun 150% -> remainder < 0", rem_150 < 0, f"got {rem_150}")

    # День 1 -> темпа нет (None)
    t_day1 = envelope_tempo(20.0, 100.0, date(2026, 5, 1), date(2026, 5, 7), ref_date=date(2026, 5, 1))
    check("H-15.3 Day 1 -> tempo is None", t_day1 is None)

    # День 3 недели при 60% трат (лимит 100, потрачено 60) -> elapsed = 3/7 = 0.4286, ratio = 0.6 / 0.4286 = 1.4 -> danger
    t_day3 = envelope_tempo(60.0, 100.0, date(2026, 5, 4), date(2026, 5, 10), ref_date=date(2026, 5, 6))
    check("H-15.4 Day 3 at 60% -> ratio=1.4 danger", t_day3 is not None and t_day3["status"] == "danger" and abs(t_day3["ratio"] - 1.4) < 0.02, f"got {t_day3}")

    # -------------------------------------------------------------
    # Prepare Fresh DB for Data Scenarios
    # -------------------------------------------------------------
    reset_db()
    init_db()
    set_setting("usd_rate", "3.0")
    set_setting("eur_rate", "3.3")

    src_id = create_income_source("Работа", "regular", 3000.0, "monthly", "BYN")
    cat_food = create_budget_category("Продукты", 200.0, "week", "BYN", is_fixed=0)
    cat_rent = create_budget_category("Аренда", 400.0, "month", "BYN", is_fixed=1)

    # -------------------------------------------------------------
    # H-2: Income 1000, dep 300, withdraw_spent 200 -> SR = 10%
    # -------------------------------------------------------------
    create_income_entry(src_id, 1000.0, "2026-01-15", "Зарплата", "BYN")
    goal_res = create_savings_goal("Подушка", "reserve", 10000.0, None, "BYN")
    create_savings_entry(goal_res, 300.0, "2026-01-15", "Депозит", "BYN", kind="deposit")
    withdraw_from_goal(goal_res, 200.0, "BYN", "2026-01-15", "spent", category_id=cat_food)

    m_jan = get_period_metrics(date(2026, 1, 1), date(2026, 1, 31))
    # NetSave = Dep(300) - W_free(0) - W_spent(200) = 100
    # SR = max(0, 100) / 1000 * 100 = 10.0%
    sr = round((max(0.0, m_jan.net_save) / m_jan.inc) * 100, 1)
    surplus = round(((m_jan.inc - m_jan.exp_all) / m_jan.inc) * 100, 1)
    check("H-2.1 SR = 10% on NetSave=100 / Inc=1000", abs(sr - 10.0) < 0.01, f"got {sr}%")
    # Exp_all = Exp_own(0) + Exp_goal(200) = 200. Surplus = (1000 - 200)/1000 = 80%
    check("H-2.2 Surplus = 80%", abs(surplus - 80.0) < 0.01, f"got {surplus}%")

    # -------------------------------------------------------------
    # H-16: Invariant Exp_goal == sum(withdraw_spent)
    # -------------------------------------------------------------
    check("H-16 Exp_goal == sum(withdraw_spent)", abs(m_jan.exp_goal - m_jan.w_spent) < 0.005, f"exp_goal={m_jan.exp_goal}, w_spent={m_jan.w_spent}")

    # -------------------------------------------------------------
    # H-1 & H-13: CashFlow equals old Free formula & Waterfall sum == CashFlow for 5 periods
    # -------------------------------------------------------------
    # Add some diverse entries across multiple periods
    create_income_entry(src_id, 2000.0, "2026-02-10", "Аванс", "BYN")
    create_budget_entry(cat_food, 350.0, "2026-02-12", "Еда", "BYN")
    create_budget_entry(cat_rent, 400.0, "2026-02-14", "Аренда", "BYN")
    create_savings_entry(goal_res, 500.0, "2026-02-15", "В копилку", "BYN", kind="deposit")
    withdraw_from_goal(goal_res, 100.0, "BYN", "2026-02-20", "free")
    add_debt_entry("Друг", "i_paid", 50.0, "BYN", "2026-02-22")

    periods_to_test = [
        (date(2026, 1, 1), date(2026, 1, 31)),
        (date(2026, 2, 1), date(2026, 2, 28)),
        (date(2026, 1, 1), date(2026, 2, 28)),
        (date(2026, 2, 10), date(2026, 2, 20)),
        (date(2026, 1, 15), date(2026, 2, 15)),
    ]

    for idx, (p_start, p_end) in enumerate(periods_to_test, 1):
        m = get_period_metrics(p_start, p_end)
        expected_free = m.inc - m.exp_own - m.dep + m.w_free - m.delta_b + m.adj_net
        check(f"H-1.{idx} CashFlow == former Free for period {p_start}..{p_end}", abs(m.cash_flow - expected_free) < 0.005, f"cf={m.cash_flow}, free={expected_free}")

        # Waterfall sum
        wf = cash_flow_waterfall(p_start, p_end)
        wf_step_sum = sum(s["amount"] for s in wf["steps"] if s["type"] != "total")
        check(f"H-13.{idx} Waterfall component steps sum == CashFlow for period {p_start}..{p_end}", abs(wf_step_sum - m.cash_flow) < 0.005, f"sum={wf_step_sum}, cf={m.cash_flow}")

    # -------------------------------------------------------------
    # H-4: History window & AvgExp: 21 days data, exp 600 -> AvgExp = 869.7; <14 days -> None
    # -------------------------------------------------------------
    h_21 = 21 / 30.4375
    avg_exp_21 = round(600.0 / h_21, 1)
    check("H-4.1 21 days data, 600 exp -> AvgExp ~ 869.7", abs(avg_exp_21 - 869.7) < 0.2, f"got {avg_exp_21}")

    ref_fresh = date(2026, 1, 20)  # first entry is 2026-01-15 -> 5 days
    h_fresh = history_months(ref_fresh, 90)
    check("H-4.2 < 14 days history -> None", h_fresh is None, f"got {h_fresh}")

    # -------------------------------------------------------------
    # H-3: reserve 1000, big 3000, exp 800/mo -> R = 1.25 ("Минимум")
    # -------------------------------------------------------------
    goal_big = create_savings_goal("Машина", "big", 50000.0, None, "BYN")
    create_savings_entry(goal_big, 3000.0, "2026-02-15", "На авто", "BYN", kind="deposit")
    create_savings_entry(goal_res, 900.0, "2026-02-15", "Подушка до 1000", "BYN", kind="deposit")
    # Current reserve: 300 - 200 + 500 - 100 + 900 = 1400. Let's adjust to exactly 1000:
    withdraw_from_goal(goal_res, 400.0, "BYN", "2026-02-15", "free")
    r_bal = goal_balance(goal_res)
    check("Reserve balance == 1000.0", abs(r_bal - 1000.0) < 0.005, f"got {r_bal}")

    r_val = round(r_bal / 800.0, 2)
    check("H-3.1 R = 1.25 for reserve 1000 and exp 800", abs(r_val - 1.25) < 0.01, f"got {r_val}")
    status_label = "Минимум" if r_val >= RUNWAY_THRESHOLDS["warning"] and r_val < RUNWAY_THRESHOLDS["ok"] else "Other"
    check("H-3.2 Status is 'Минимум'", status_label == "Минимум", f"got {status_label}")

    # -------------------------------------------------------------
    # H-6: Rent 400 (is_fixed=1) excluded from BurnVar; SafePerDay negative on overrun
    # -------------------------------------------------------------
    burn = calculate_daily_burn_and_forecast(date(2026, 2, 28))
    check("H-6.1 Rent (is_fixed=1) excluded from BurnVar", abs(burn["burn_var"] - 12.50) < 0.05, f"got burn_var={burn['burn_var']}")

    # Overrun safe_per_day check:
    create_budget_entry(cat_food, 300.0, "2026-02-25", "Еда перерасход", "BYN")
    burn_over = calculate_daily_burn_and_forecast(date(2026, 2, 26))
    check("H-6.2 SafePerDay is negative on overrun", burn_over["safe_per_day"] < 0, f"got {burn_over['safe_per_day']}")

    # -------------------------------------------------------------
    # H-7: Pareto core calculation for 6 categories; < 5 note
    # -------------------------------------------------------------
    reset_db()
    init_db()
    c1 = create_budget_category("Cat1", 1000.0, "month", "BYN", is_fixed=0)
    c2 = create_budget_category("Cat2", 1000.0, "month", "BYN", is_fixed=0)
    c3 = create_budget_category("Cat3", 1000.0, "month", "BYN", is_fixed=0)
    c4 = create_budget_category("Cat4", 1000.0, "month", "BYN", is_fixed=0)
    c5 = create_budget_category("Cat5", 1000.0, "month", "BYN", is_fixed=0)
    c6 = create_budget_category("Cat6", 1000.0, "month", "BYN", is_fixed=0)

    d_now = date(2026, 3, 20)
    create_budget_entry(c1, 500.0, "2026-03-05", "c1", "BYN")
    create_budget_entry(c2, 200.0, "2026-03-06", "c2", "BYN")
    create_budget_entry(c3, 150.0, "2026-03-07", "c3", "BYN")
    create_budget_entry(c4, 50.0, "2026-03-08", "c4", "BYN")
    create_budget_entry(c5, 50.0, "2026-03-09", "c5", "BYN")
    create_budget_entry(c6, 50.0, "2026-03-10", "c6", "BYN")

    p_res = category_comparison_and_pareto(d_now)
    check("H-7.1 Pareto core has 3 categories", len(p_res["pareto_core"]) == 3, f"got {p_res['pareto_core']}")
    check("H-7.2 Core is Cat1, Cat2, Cat3", set(p_res["pareto_core"]) == {"Cat1", "Cat2", "Cat3"}, f"got {p_res['pareto_core']}")
    check("H-7.3 few_categories is False for 6 categories", p_res["few_categories"] is False)

    # -------------------------------------------------------------
    # H-8: Day 15: 400 vs 420 -> -4.8%
    # -------------------------------------------------------------
    reset_db()
    init_db()
    c_shop = create_budget_category("Шоппинг", 1000.0, "month", "BYN", is_fixed=0)
    create_budget_entry(c_shop, 420.0, "2026-02-10", "Магазин фев", "BYN")
    create_budget_entry(c_shop, 400.0, "2026-03-12", "Магазин мар", "BYN")
    shift_res = category_comparison_and_pareto(date(2026, 3, 15))
    shop_item = next(c for c in shift_res["all_categories"] if c["id"] == c_shop)
    check("H-8 Day 15 honest comparison: -4.8%", abs(shop_item["pct_change"] - (-4.8)) < 0.1, f"got {shop_item['pct_change']}%")

    # -------------------------------------------------------------
    # H-9: usd_rate 3.0 -> 3.3 historical BYN and USD goal balance unchanged
    # -------------------------------------------------------------
    set_setting("usd_rate", "3.0")
    set_setting("eur_rate", "3.3")
    g_usd = create_savings_goal("USD Fund", "want", 1000.0, None, "USD")
    create_savings_entry(g_usd, 100.0, "2026-03-01", "USD dep", "USD", kind="deposit")
    c_usd_exp = create_budget_entry(c_shop, 50.0, "2026-03-02", "USD buy", "USD")

    with get_db() as conn:
        b_entry = conn.execute("SELECT amount_byn, rate_usd FROM budget_entries WHERE id = ?", (c_usd_exp,)).fetchone()
        check("H-9.1 Entry created with rate_usd=3.0 and amount_byn=150.0", abs(b_entry["amount_byn"] - 150.0) < 0.005 and abs(b_entry["rate_usd"] - 3.0) < 0.005)

    set_setting("usd_rate", "3.3")

    with get_db() as conn:
        b_entry_after = conn.execute("SELECT amount_byn FROM budget_entries WHERE id = ?", (c_usd_exp,)).fetchone()
        check("H-9.2 Historical amount_byn unchanged after rate update", abs(b_entry_after["amount_byn"] - 150.0) < 0.005)

    g_bal = goal_balance(g_usd)
    check("H-9.3 Goal balance in native USD is unchanged (100.0)", abs(g_bal - 100.0) < 0.005, f"got {g_bal}")

    # -------------------------------------------------------------
    # H-10: 100 USD rate change 3.0 -> 3.3 -> fx_effect=30.0, diff_clean=0, no Неучтёнка
    # -------------------------------------------------------------
    reset_db()
    init_db()
    set_setting("usd_rate", "3.0")
    save_check(
        real_breakdown={"byn": 0.0, "usd": 100.0, "eur": 0.0},
        check_date="2026-03-01",
        comment="Check 1",
    )
    set_setting("usd_rate", "3.3")
    exp_calc = calculate_expected(330.0, "2026-03-08")
    check("H-10.1 fx_effect == 30.0", abs(exp_calc["fx_effect"] - 30.0) < 0.01, f"got {exp_calc['fx_effect']}")
    check("H-10.2 diff_clean == 0.0", abs(exp_calc["diff_clean"] - 0.0) < 0.01, f"got {exp_calc['diff_clean']}")

    # -------------------------------------------------------------
    # H-11: Shortage 15 -> Adj_exp=15; Inc, Exp_all, SR, Pareto unchanged; CashFlow down by 15; accuracy < 100%
    # -------------------------------------------------------------
    src_w = create_income_source("Работа", "regular", 1000.0, "monthly", "BYN")
    create_income_entry(src_w, 1000.0, "2026-03-02", "ЗП", "BYN")
    c_var = create_budget_category("Разное", 500.0, "month", "BYN", is_fixed=0)
    create_budget_entry(c_var, 200.0, "2026-03-03", "Расход", "BYN")

    save_check(
        real_breakdown={"byn": 785.0, "usd": 100.0, "eur": 0.0},
        check_date="2026-03-08",
        comment="Shortage 15",
    )
    m_reconciled = get_period_metrics(date(2026, 3, 1), date(2026, 3, 31))
    check("H-11.1 Adj_exp == 15.0", abs(m_reconciled.adj_exp - 15.0) < 0.005, f"got {m_reconciled.adj_exp}")
    check("H-11.2 Inc unchanged at 1000.0", abs(m_reconciled.inc - 1000.0) < 0.005, f"got {m_reconciled.inc}")
    check("H-11.3 Exp_all unchanged at 200.0", abs(m_reconciled.exp_all - 200.0) < 0.005, f"got {m_reconciled.exp_all}")
    check("H-11.4 CashFlow includes -15 adjustment", abs(m_reconciled.adj_net - (-15.0)) < 0.005)
    acc_res = calculate_accounting_accuracy(date(2026, 3, 15))
    check("H-11.5 Accuracy < 100%", acc_res["accuracy_pct"] < 100.0, f"got {acc_res['accuracy_pct']}%")

    # -------------------------------------------------------------
    # H-12: Goal 1200, current 300, window 2 mo (dep 300) -> Pace=150, deadline in 4 mo -> Required=225, "Отстаёт"
    # -------------------------------------------------------------
    reset_db()
    init_db()
    g_target = create_savings_goal("Отпуск", "want", 1200.0, "2026-07-01", "BYN")
    create_savings_entry(g_target, 300.0, "2026-01-01", "Взнос", "BYN", kind="deposit")
    g_res = goals_analytics(date(2026, 3, 2))
    g_item = next(g for g in g_res if g["id"] == g_target)
    check("H-12.1 Pace ~ 150/mo", abs(g_item["monthly_pace"] - 150.0) < 10.0, f"got {g_item['monthly_pace']}")
    check("H-12.2 Required ~ 225/mo", abs(g_item["required_monthly"] - 225.0) < 15.0, f"got {g_item['required_monthly']}")
    check("H-12.3 Status is 'behind' ('Отстаёт')", g_item["deadline_status"] == "behind", f"got {g_item['deadline_status']}")

    # -------------------------------------------------------------
    # H-5: Budget adherence over closed periods
    # -------------------------------------------------------------
    reset_db()
    init_db()
    c_adh = create_budget_category("Обеды", 100.0, "week", "BYN", is_fixed=0)
    with get_db() as conn:
        conn.execute("UPDATE budget_categories SET created_at = '2026-02-01 00:00:00' WHERE id = ?", (c_adh,))
    create_budget_entry(c_adh, 80.0, "2026-02-03", "нед1", "BYN")
    create_budget_entry(c_adh, 120.0, "2026-02-10", "нед2", "BYN")
    create_budget_entry(c_adh, 50.0, "2026-02-17", "нед3", "BYN")
    adh_res = calculate_budget_adherence(date(2026, 3, 1))
    check("H-5.1 Adherence calculated over closed periods", abs(adh_res["adherence_pct"] - 66.7) < 1.0, f"got {adh_res['adherence_pct']}%")

    # -------------------------------------------------------------
    # H-17: 6-month trends averages exclude current month
    # -------------------------------------------------------------
    src_inc = create_income_source("Доход", "regular", 2000.0, "monthly", "BYN")
    create_income_entry(src_inc, 1000.0, "2026-01-10", "янв", "BYN")
    create_income_entry(src_inc, 2000.0, "2026-02-10", "фев", "BYN")
    create_income_entry(src_inc, 9000.0, "2026-03-10", "мар выброс", "BYN")

    tr = six_months_trends(date(2026, 3, 15))
    check("H-17 Trends average income excludes current month (got 1500, not 4000)", abs(tr["summary"]["avg_income"] - 1500.0) < 0.01, f"got {tr['summary']['avg_income']}")

    print("\n=== Все аналитические тесты H-1 ... H-17 успешно пройдены! ===")
    return True


if __name__ == "__main__":
    run_tests()
