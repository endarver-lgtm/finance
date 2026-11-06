import json
from datetime import date, timedelta
from typing import Optional

from db import get_db, rows_to_dicts, get_setting
from services.constants import (
    ACCURACY_THRESHOLDS,
    ADHERENCE_THRESHOLDS,
    BASE_CURRENCY,
    ONE_TIME_INCOME_LABEL,
    RUNWAY_THRESHOLDS,
    SAVINGS_RATE_THRESHOLDS,
)
from services.currency import (
    convert_at_entry,
    normalize_currency,
    to_byn,
    usd_rate,
)
from services.dates import (
    add_months,
    last_n_months,
    month_label,
    month_start,
    parse_date,
    period_bounds,
    to_iso,
)
from services.debts import delta_b
from services.metrics_core import (
    PeriodMetrics,
    get_first_entry_date,
    get_period_metrics,
    history_months,
)
from services.planning import (
    budget_planned_for_period,
    category_planned_for_period,
    income_planned_for_period,
    scale_plan,
)
from services.progress import envelope_tempo, income_status, progress_color, usage_percent
from services.repository import sum_in_range_byn
from services.savings import goal_balance


# ==============================================================================
# Backward-compatible delegation helpers (used by tests & existing routes)
# ==============================================================================

def income_fact(start: date, end: date) -> float:
    """Фактический доход без корректировок сверки (Inc)."""
    return get_period_metrics(start, end).inc


def budget_fact_own(start: date, end: date) -> float:
    """Собственные расходы (Exp_own) без трат из копилок и без корректировок сверки."""
    return get_period_metrics(start, end).exp_own


def budget_fact_from_goals(start: date, end: date) -> float:
    """Расходы из копилок (Exp_goal)."""
    return get_period_metrics(start, end).exp_goal


def budget_fact_all(start: date, end: date) -> float:
    """Все расходы (Exp_all = Exp_own + Exp_goal) — база аналитики трат."""
    return get_period_metrics(start, end).exp_all


def savings_deposits_for_period(start: date, end: date) -> float:
    return get_period_metrics(start, end).dep


def savings_withdraw_free_for_period(start: date, end: date) -> float:
    return get_period_metrics(start, end).w_free


def savings_withdraw_spent_for_period(start: date, end: date) -> float:
    return get_period_metrics(start, end).w_spent


def free_cash_flow(start: date, end: date) -> float:
    """Чистый денежный поток (CashFlow). Равен прежнему Free (регресс инвариант)."""
    return get_period_metrics(start, end).cash_flow


def savings_total(target_currency: str = BASE_CURRENCY) -> float:
    """Суммарный остаток во всех копилках в указанной валюте (по курсам операций)."""
    with get_db() as conn:
        goals = conn.execute("SELECT id, currency FROM savings_goals").fetchall()
    total_native = 0.0
    for g in goals:
        b = goal_balance(g["id"], g["currency"])
        total_native += to_byn(b, g["currency"])
    return round(total_native, 2)


def reserve_savings_total() -> float:
    """Суммарный остаток только в копилках типа 'reserve' (C2)."""
    with get_db() as conn:
        goals = conn.execute("SELECT id, currency FROM savings_goals WHERE type = 'reserve'").fetchall()
    total = 0.0
    for g in goals:
        b = goal_balance(g["id"], g["currency"])
        total += to_byn(b, g["currency"])
    return round(total, 2)


def expenses_by_category(start: date, end: date, include_fixed: bool = True):
    """Структура расходов по категориям за период (по Exp_all)."""
    with get_db() as conn:
        sql = "SELECT id, name, is_fixed FROM budget_categories WHERE track_only = 0"
        if not include_fixed:
            sql += " AND is_fixed = 0"
        cats = rows_to_dicts(conn.execute(sql).fetchall())

    result = []
    for c in cats:
        spent = sum_in_range_byn(
            "budget_entries",
            "date",
            start,
            end,
            "category_id = ? AND id NOT IN (SELECT adjust_expense_id FROM balance_checks WHERE adjust_expense_id IS NOT NULL)",
            (c["id"],),
        )
        result.append({"id": c["id"], "name": c["name"], "spent": spent, "is_fixed": c.get("is_fixed", 0)})
    result.sort(key=lambda x: (-x["spent"], x["name"]))
    return result


def income_by_months(months):
    """Динамика доходов по месяцам для графиков."""
    labels, plan, fact = [], [], []
    for m_start, m_end in months:
        labels.append(month_label(m_start))
        plan.append(income_planned_for_period("month", m_start))
        fact.append(income_fact(m_start, m_end))
    return labels, plan, fact


def envelope_progress(period: str = "week", ref: Optional[date] = None):
    """
    Прогресс конвертов с честной полоской (E1) и расчетом темпа (E2).
    """
    ref = ref or date.today()
    start, end = period_bounds(period, ref)
    result = []
    with get_db() as conn:
        cats = rows_to_dicts(
            conn.execute(
                "SELECT * FROM budget_categories WHERE track_only = 0 ORDER BY is_fixed ASC, name ASC"
            ).fetchall()
        )

    for c in cats:
        cur = c.get("currency", "BYN")
        cat_period = c.get("period", "month")
        # Масштабирование плана через scale_plan (D1)
        planned_native = scale_plan(float(c.get("planned_amount") or 0), cat_period, start, end)
        planned_byn = to_byn(planned_native, cur)

        spent = sum_in_range_byn(
            "budget_entries",
            "date",
            start,
            end,
            "category_id = ? AND from_goal_id IS NULL AND id NOT IN (SELECT adjust_expense_id FROM balance_checks WHERE adjust_expense_id IS NOT NULL)",
            (c["id"],),
        )

        # E1: Честный процент и остаток без искусственного обнуления
        pct = usage_percent(spent, planned_byn, clamp=False)
        remaining = round(planned_byn - spent, 2)
        pct_status = progress_color(pct)

        # E2: Темп расходования
        tempo = envelope_tempo(spent, planned_byn, start, end, ref)
        tempo_status = tempo["status"] if tempo else "ok"

        # Итоговый статус карточки — худший из pct и tempo
        severity_order = {"danger": 3, "warning": 2, "ok": 1}
        worst_severity = max(severity_order.get(pct_status, 1), severity_order.get(tempo_status, 1))
        overall_status = "danger" if worst_severity == 3 else ("warning" if worst_severity == 2 else "ok")

        result.append({
            "id": c["id"],
            "name": c["name"],
            "period": cat_period,
            "is_fixed": c.get("is_fixed", 0),
            "planned": planned_native,
            "planned_currency": cur,
            "planned_byn": planned_byn,
            "spent": spent,
            "remaining": remaining,
            "pct": pct,
            "status": overall_status,
            "pct_status": pct_status,
            "tempo": tempo,
        })
    return result


def upcoming_income(ref: Optional[date] = None):
    """
    Календарь ожидаемых поступлений (D2, D3).
    Учитывает expected_date разовых доходов и pay_days регулярных.
    """
    ref = ref or date.today()
    start, end = period_bounds("month", ref)
    items = []
    with get_db() as conn:
        sources = rows_to_dicts(
            conn.execute(
                """
                SELECT * FROM income_sources
                WHERE active = 1
                ORDER BY name
                """
            ).fetchall()
        )

    for s in sources:
        cur = s.get("currency", "BYN")
        planned_raw = float(s.get("planned_amount") or 0)
        stype = s.get("type", "regular")
        freq = s.get("frequency", "monthly")
        exp_date_str = s.get("expected_date")

        # Суммируем факт за текущий месяц
        fact = sum_in_range_byn(
            "income_entries",
            "date",
            start,
            end,
            "source_id = ? AND id NOT IN (SELECT adjust_income_id FROM balance_checks WHERE adjust_income_id IS NOT NULL)",
            (s["id"],),
        )

        if stype == "one_time" or freq == "one_time":
            # Показываем разовый доход, если он относится к этому месяцу или просрочен
            exp_d = parse_date(exp_date_str)
            if not exp_d and s.get("created_at"):
                exp_d = parse_date(s["created_at"][:10])

            if exp_d and (exp_d <= end or fact > 0):
                status = income_status(fact, planned_raw, exp_date_str, ref)
                items.append({
                    "id": s["id"],
                    "name": s["name"],
                    "planned": planned_raw,
                    "planned_currency": cur,
                    "fact": fact,
                    "fact_currency": "BYN",
                    "status": status,
                    "expected_date": exp_date_str,
                    "is_one_time": True,
                })
        else:
            # Регулярный доход
            planned_scaled = scale_plan(planned_raw, freq, start, end)
            status = income_status(fact, planned_scaled, None, ref)
            items.append({
                "id": s["id"],
                "name": s["name"],
                "planned": planned_scaled,
                "planned_currency": cur,
                "fact": fact,
                "fact_currency": "BYN",
                "status": status,
                "expected_date": None,
                "is_one_time": False,
            })
    return items


def history_rows(
    date_from: Optional[date],
    date_to: Optional[date],
    type_filter: str,
    category_filter: str,
):
    """История всех операций с фильтрацией."""
    rows = []
    clause, params = _date_filter_clause("e.date", date_from, date_to)

    if type_filter in ("", "income"):
        with get_db() as conn:
            for r in conn.execute(
                f"""
                SELECT e.id, e.date, e.amount, e.currency, e.amount_byn, e.comment, e.source_id,
                       COALESCE(s.name, '{ONE_TIME_INCOME_LABEL}') AS label,
                       'income' AS kind
                FROM income_entries e
                LEFT JOIN income_sources s ON s.id = e.source_id
                WHERE {clause}
                ORDER BY e.date DESC, e.id DESC
                """,
                params,
            ).fetchall():
                row = dict(r)
                if category_filter and row["label"] != category_filter:
                    continue
                rows.append(row)

    if type_filter in ("", "expense"):
        with get_db() as conn:
            for r in conn.execute(
                f"""
                SELECT e.id, e.date, e.amount, e.currency, e.amount_byn, e.comment, e.category_id,
                       c.name AS label, 'expense' AS kind, e.from_goal_id, g.name AS goal_name
                FROM budget_entries e
                JOIN budget_categories c ON c.id = e.category_id
                LEFT JOIN savings_goals g ON g.id = e.from_goal_id
                WHERE {clause}
                ORDER BY e.date DESC, e.id DESC
                """,
                params,
            ).fetchall():
                row = dict(r)
                if category_filter and row["label"] != category_filter:
                    continue
                rows.append(row)

    if type_filter in ("", "savings", "savings_withdraw"):
        clause_s, params_s = _date_filter_clause("e.date", date_from, date_to)
        with get_db() as conn:
            for r in conn.execute(
                f"""
                SELECT e.id, e.date, e.amount, e.currency, e.amount_byn, e.comment, e.goal_id,
                       g.name AS label, e.kind AS entry_kind
                FROM savings_entries e
                JOIN savings_goals g ON g.id = e.goal_id
                WHERE {clause_s}
                ORDER BY e.date DESC, e.id DESC
                """,
                params_s,
            ).fetchall():
                row = dict(r)
                if category_filter and row["label"] != category_filter:
                    continue
                e_kind = row.get("entry_kind") or "deposit"
                row_kind = "savings" if e_kind == "deposit" else "savings_withdraw"
                if type_filter and type_filter != row_kind:
                    continue
                row["kind"] = row_kind
                row["raw_kind"] = e_kind
                rows.append(row)

    if type_filter in ("", "debt"):
        clause_d, params_d = _date_filter_clause("d.date", date_from, date_to)
        with get_db() as conn:
            for r in conn.execute(
                f"""
                SELECT d.id, d.date, d.amount, d.currency, d.amount_byn, d.comment, d.person,
                       d.person AS label, 'debt' AS kind, d.kind AS debt_kind
                FROM debts d
                WHERE {clause_d}
                ORDER BY d.date DESC, d.id DESC
                """,
                params_d,
            ).fetchall():
                row = dict(r)
                if category_filter and row["label"] != category_filter:
                    continue
                d_kind = row.get("debt_kind")
                row["sign"] = "+" if d_kind in ("i_paid", "repay_to_him") else "−"
                rows.append(row)

    rows.sort(key=lambda x: (x["date"], x["id"]), reverse=True)
    return rows


def _date_filter_clause(col: str, date_from, date_to):
    parts, params = [], []
    if date_from:
        parts.append(f"{col} >= ?")
        params.append(to_iso(date_from))
    if date_to:
        parts.append(f"{col} <= ?")
        params.append(to_iso(date_to))
    return (" AND ".join(parts), params) if parts else ("1=1", [])


# ==============================================================================
# Comprehensive Analytics Center (Stages C1 - C10)
# ==============================================================================

def calculate_budget_adherence(ref: Optional[date] = None) -> dict:
    """
    Дисциплина бюджета по закрытым периодам (C3):
    - Недельные конверты: последние 8 закрытых недель (ISO).
    - Месячные конверты: последние 3 закрытых месяца.
    - Учитываются только периоды, начинающиеся ПОСЛЕ created_at конверта.
    - Единица учёта: пара (конверт, период), Spent_own <= Limit.
    """
    ref = ref or date.today()

    # 1. 8 закрытых недель (пн - вс)
    this_monday = ref - timedelta(days=ref.weekday())
    closed_weeks = []
    for i in range(1, 9):
        w_end = this_monday - timedelta(days=1 + (i - 1) * 7)
        w_start = w_end - timedelta(days=6)
        closed_weeks.append((w_start, w_end))

    # 2. 3 закрытых месяца
    this_month_start = date(ref.year, ref.month, 1)
    closed_months = []
    curr_m_start = this_month_start
    for _ in range(3):
        m_end = curr_m_start - timedelta(days=1)
        m_start = date(m_end.year, m_end.month, 1)
        closed_months.append((m_start, m_end))
        curr_m_start = m_start

    with get_db() as conn:
        cats = rows_to_dicts(
            conn.execute(
                """
                SELECT id, name, period, planned_amount, currency, created_at
                FROM budget_categories
                WHERE track_only = 0 AND planned_amount > 0
                """
            ).fetchall()
        )

    total_pairs = 0
    in_limit_pairs = 0
    overruns = []

    for c in cats:
        cat_cur = c.get("currency", "BYN")
        cat_limit = to_byn(float(c.get("planned_amount") or 0), cat_cur)
        if cat_limit <= 0.005:
            continue

        cat_created_str = (c.get("created_at") or "")[:10]
        cat_created = parse_date(cat_created_str) or date(2000, 1, 1)

        periods_to_check = closed_weeks if c["period"] == "week" else closed_months

        for p_start, p_end in periods_to_check:
            # Учитывать только периоды, начавшиеся ПОСЛЕ создания конверта
            if p_start < cat_created:
                continue

            spent = sum_in_range_byn(
                "budget_entries",
                "date",
                p_start,
                p_end,
                "category_id = ? AND from_goal_id IS NULL AND id NOT IN (SELECT adjust_expense_id FROM balance_checks WHERE adjust_expense_id IS NOT NULL)",
                (c["id"],),
            )

            total_pairs += 1
            if spent <= cat_limit + 0.005:
                in_limit_pairs += 1
            else:
                overruns.append((spent / cat_limit) - 1.0)

    if total_pairs == 0:
        return {
            "adherence_pct": None,
            "status": "none",
            "label": "Мало данных",
            "total_pairs": 0,
            "in_limit_pairs": 0,
            "avg_overrun_pct": None,
        }

    pct = round((in_limit_pairs / total_pairs) * 100, 1)
    status = "ok" if pct >= ADHERENCE_THRESHOLDS["ok"] else "warning"
    avg_overrun = round((sum(overruns) / len(overruns)) * 100, 1) if overruns else 0.0

    return {
        "adherence_pct": pct,
        "status": status,
        "label": f"{in_limit_pairs} из {total_pairs}",
        "total_pairs": total_pairs,
        "in_limit_pairs": in_limit_pairs,
        "avg_overrun_pct": avg_overrun,
    }


def calculate_daily_burn_and_forecast(ref: Optional[date] = None) -> dict:
    """
    Расчет дневного расхода, «можно тратить в день» и прогноза на месяц (C4).
    """
    ref = ref or date.today()
    m_start, m_end = period_bounds("month", ref)

    passed_days = max(1, (ref - m_start).days + 1)
    days_in_month = (m_end - m_start).days + 1
    remaining_days = max(0, (m_end - ref).days)

    with get_db() as conn:
        var_cats = rows_to_dicts(
            conn.execute(
                """
                SELECT id, name, period, planned_amount, currency
                FROM budget_categories
                WHERE track_only = 0 AND is_fixed = 0
                """
            ).fetchall()
        )
        fixed_cats = rows_to_dicts(
            conn.execute(
                """
                SELECT id, name, period, planned_amount, currency
                FROM budget_categories
                WHERE track_only = 0 AND is_fixed = 1
                """
            ).fetchall()
        )

    # 1. BurnVar: Exp_all по переменным конвертам за месяц на сегодня / прошедшие дни
    var_cat_ids = [c["id"] for c in var_cats]
    if var_cat_ids:
        placeholders = ",".join("?" for _ in var_cat_ids)
        spent_var_month = sum_in_range_byn(
            "budget_entries",
            "date",
            m_start,
            ref,
            f"category_id IN ({placeholders}) AND id NOT IN (SELECT adjust_expense_id FROM balance_checks WHERE adjust_expense_id IS NOT NULL)",
            var_cat_ids,
        )
    else:
        spent_var_month = 0.0

    burn_var = round(spent_var_month / passed_days, 2)

    # 2. SafePerDay: Σ по переменным конвертам [лимит_периода − Spent_own] / дни до конца периода
    safe_daily_total = 0.0
    for vc in var_cats:
        vcur = vc.get("currency", "BYN")
        vperiod = vc.get("period", "month")
        if vperiod == "week":
            w_start, w_end = period_bounds("week", ref)
            days_left = max(1, (w_end - ref).days + 1)
            vlimit = to_byn(float(vc.get("planned_amount") or 0), vcur)
            vspent = sum_in_range_byn(
                "budget_entries",
                "date",
                w_start,
                ref,
                "category_id = ? AND from_goal_id IS NULL AND id NOT IN (SELECT adjust_expense_id FROM balance_checks WHERE adjust_expense_id IS NOT NULL)",
                (vc["id"],),
            )
        else:
            days_left = max(1, (m_end - ref).days + 1)
            vlimit = to_byn(float(vc.get("planned_amount") or 0), vcur)
            vspent = sum_in_range_byn(
                "budget_entries",
                "date",
                m_start,
                ref,
                "category_id = ? AND from_goal_id IS NULL AND id NOT IN (SELECT adjust_expense_id FROM balance_checks WHERE adjust_expense_id IS NOT NULL)",
                (vc["id"],),
            )
        safe_daily_total += (vlimit - vspent) / days_left

    safe_per_day = round(safe_daily_total, 2)

    # 3. Forecast месяца:
    # Exp_all_месяца_на_сегодня + BurnVar * оставшиеся_дни + невыплаченные_фиксированные
    exp_all_month_today = sum_in_range_byn(
        "budget_entries",
        "date",
        m_start,
        ref,
        "id NOT IN (SELECT adjust_expense_id FROM balance_checks WHERE adjust_expense_id IS NOT NULL)",
    )

    unpaid_fixed = 0.0
    for fc in fixed_cats:
        fcur = fc.get("currency", "BYN")
        flimit = to_byn(float(fc.get("planned_amount") or 0), fcur)
        fspent = sum_in_range_byn(
            "budget_entries",
            "date",
            m_start,
            ref,
            "category_id = ? AND id NOT IN (SELECT adjust_expense_id FROM balance_checks WHERE adjust_expense_id IS NOT NULL)",
            (fc["id"],),
        )
        if fspent <= 0.005:
            unpaid_fixed += flimit
        else:
            unpaid_fixed += max(0.0, flimit - fspent)

    forecast_month = round(exp_all_month_today + (burn_var * remaining_days) + unpaid_fixed, 2)

    return {
        "burn_var": burn_var,
        "safe_per_day": safe_per_day,
        "forecast_month": forecast_month,
        "passed_days": passed_days,
        "remaining_days": remaining_days,
    }


def calculate_accounting_accuracy(ref: Optional[date] = None) -> dict:
    """
    Точность учёта (C10):
    Unexplained = Adj_inc + Adj_exp за последние 30 дней.
    Точность = 100% − Unexplained / (Exp_all + Adj_exp).
    """
    ref = ref or date.today()
    start_30 = ref - timedelta(days=29)
    m = get_period_metrics(start_30, ref)

    unexplained = round(abs(m.adj_inc) + abs(m.adj_exp), 2)
    denominator = round(m.exp_all + abs(m.adj_exp), 2)

    if denominator <= 0.005:
        return {
            "accuracy_pct": None,
            "status": "none",
            "label": "Мало данных",
            "unexplained_byn": unexplained,
        }

    unexplained_ratio = (unexplained / denominator) * 100
    accuracy_pct = max(0.0, min(100.0, round(100.0 - unexplained_ratio, 1)))

    if unexplained_ratio <= ACCURACY_THRESHOLDS["ok"]:
        status = "ok"
        label = "Высокая"
    elif unexplained_ratio <= ACCURACY_THRESHOLDS["warning"]:
        status = "warning"
        label = "Норма"
    else:
        status = "danger"
        label = "Низкая"

    return {
        "accuracy_pct": accuracy_pct,
        "status": status,
        "label": label,
        "unexplained_byn": unexplained,
        "unexplained_pct": round(unexplained_ratio, 1),
    }


def health_metrics(start: date, end: date, ref: Optional[date] = None) -> dict:
    """
    Расчёт интегральных метрик финансового здоровья на базе metrics_core (C1, C2, C3, C4, C10).
    """
    ref = ref or date.today()
    m = get_period_metrics(start, end)

    # 1. Savings Rate (C1)
    if m.inc > 0.005:
        savings_rate = round((max(0.0, m.net_save) / m.inc) * 100, 1)
        surplus_rate = round(((m.inc - m.exp_all) / m.inc) * 100, 1)
        if savings_rate >= SAVINGS_RATE_THRESHOLDS["ok"]:
            sr_status, sr_label = "ok", "Отлично"
        elif savings_rate >= SAVINGS_RATE_THRESHOLDS["warning"]:
            sr_status, sr_label = "warning", "Норма"
        else:
            sr_status, sr_label = "danger", "Низкая"
    else:
        savings_rate = None
        surplus_rate = None
        sr_status, sr_label = "none", "Мало данных"

    # 2. Runway (Подушка безопасности в месяцах) (C2)
    reserve_savings = reserve_savings_total()
    all_savings = savings_total()

    h_months = history_months(ref, window_days=90)
    past_90_start = ref - timedelta(days=89)
    past_90_metrics = get_period_metrics(past_90_start, ref)

    if h_months is not None and h_months > 0:
        avg_monthly_exp = round(past_90_metrics.exp_all / h_months, 2)
    elif m.exp_all > 0:
        avg_monthly_exp = m.exp_all
    else:
        avg_monthly_exp = None

    has_reserve_goals = False
    with get_db() as conn:
        r_count = conn.execute("SELECT COUNT(*) FROM savings_goals WHERE type = 'reserve'").fetchone()[0]
        has_reserve_goals = r_count > 0

    if not has_reserve_goals:
        runway_months = None
        rw_status, rw_label = "none", "Нет резерва"
        all_savings_months = None
    elif avg_monthly_exp is not None and avg_monthly_exp > 0.01:
        runway_months = round(reserve_savings / max(avg_monthly_exp, 1.0), 1)
        all_savings_months = round(all_savings / max(avg_monthly_exp, 1.0), 1)

        if runway_months >= RUNWAY_THRESHOLDS["stellar"]:
            rw_status, rw_label = "stellar", "Капитал"
        elif runway_months >= RUNWAY_THRESHOLDS["ok"]:
            rw_status, rw_label = "ok", "Надёжно"
        elif runway_months >= RUNWAY_THRESHOLDS["warning"]:
            rw_status, rw_label = "warning", "Минимум"
        else:
            rw_status, rw_label = "danger", "Критично"
    else:
        runway_months = None
        rw_status, rw_label = "none", "Мало данных"
        all_savings_months = None

    # 3. Дисциплина бюджета (C3)
    adh = calculate_budget_adherence(ref)

    # 4. Дневной расход и темп (C4)
    burn_data = calculate_daily_burn_and_forecast(ref)

    # 5. Точность учёта (C10)
    acc = calculate_accounting_accuracy(ref)

    # Текущий период (неделя) для быстрой плашки дашборда
    env_curr = envelope_progress("week", ref)
    in_limit_curr = sum(1 for e in env_curr if e["spent"] <= e["planned_byn"] + 0.005)

    return {
        "savings_rate": savings_rate,
        "savings_rate_status": sr_status,
        "savings_rate_label": sr_label,
        "surplus_rate": surplus_rate,
        "runway_months": runway_months,
        "runway_status": rw_status,
        "runway_label": rw_label,
        "all_savings_months": all_savings_months,
        "has_reserve_goals": has_reserve_goals,
        "avg_monthly_exp": avg_monthly_exp or 0.0,
        "adherence_pct": adh["adherence_pct"],
        "adherence_status": adh["status"],
        "adherence_label": adh["label"],
        "in_limit_count": in_limit_curr,
        "total_envelopes": len(env_curr),
        "daily_burn": burn_data["burn_var"],
        "safe_per_day": burn_data["safe_per_day"],
        "forecast_month": burn_data["forecast_month"],
        "accuracy_pct": acc["accuracy_pct"],
        "accuracy_status": acc["status"],
        "accuracy_label": acc["label"],
        "unexplained_byn": acc["unexplained_byn"],
    }


def cash_flow_waterfall(start: date, end: date) -> dict:
    """
    Водопад движения денежных средств (C8) на базе metrics_core:
    Inc → −Exp_own → −Dep → +W_free → −ΔB (если ≠0) → ±Adj_net (если ≠0) = CashFlow.
    Инвариант: сумма всех шагов математически строго равна CashFlow.
    """
    m = get_period_metrics(start, end)

    steps = [
        {"label": "Доходы", "amount": m.inc, "type": "positive", "desc": "Все фактические поступления (без корректировок)"},
        {"label": "Конверты", "amount": -m.exp_own, "type": "negative", "desc": "Текущие расходы из лимитов конвертов"},
        {"label": "Взносы", "amount": -m.dep, "type": "negative", "desc": "Пополнения копилок"},
        {"label": "Возврат из копилок", "amount": m.w_free, "type": "positive", "desc": "Возврат накоплений в свободный остаток"},
    ]

    if abs(m.delta_b) > 0.005:
        steps.append({
            "label": "Долги (Δ)",
            "amount": -m.delta_b,
            "type": "negative" if m.delta_b > 0 else "positive",
            "desc": "Изменение баланса взаиморасчётов",
        })

    if abs(m.adj_net) > 0.005:
        steps.append({
            "label": "Корректировки сверки",
            "amount": m.adj_net,
            "type": "positive" if m.adj_net > 0 else "negative",
            "desc": "Скорректированные расхождения по сверкам остатков",
        })

    steps.append({
        "label": "Чистый поток",
        "amount": m.cash_flow,
        "type": "total",
        "desc": "Результирующий чистый денежный поток периода",
    })

    return {
        "income": m.inc,
        "expenses": m.exp_own,
        "exp_goal": m.exp_goal,
        "savings": m.net_save,
        "debt_delta": m.delta_b,
        "adj_net": m.adj_net,
        "free_cash": m.cash_flow,
        "steps": steps,
    }


def category_comparison_and_pareto(ref: Optional[date] = None, include_fixed: bool = False) -> dict:
    """
    Анализ структуры трат (Парето, C5) и честные сдвиги день-в-день (C6).
    """
    ref = ref or date.today()
    cur_start, cur_end = period_bounds("month", ref)

    # C6: Честное сравнение день-в-день: с 1-го по d-й день текущего vs прошлого месяца
    d = ref.day
    prev_month_ref = add_months(cur_start, -1)
    prev_start, prev_full_end = period_bounds("month", prev_month_ref)
    days_in_prev = (prev_full_end - prev_start).days + 1
    d_prev = min(d, days_in_prev)
    prev_end_d = prev_start + timedelta(days=d_prev - 1)

    with get_db() as conn:
        cats = rows_to_dicts(
            conn.execute(
                """
                SELECT id, name, is_fixed FROM budget_categories
                WHERE track_only = 0
                ORDER BY name
                """
            ).fetchall()
        )

    categories_data = []
    total_cur = 0.0
    total_prev = 0.0

    for c in cats:
        # Для Парето берется Exp_all (включая from_goal_id) без корректировок сверки
        spent_cur = sum_in_range_byn(
            "budget_entries", "date", cur_start, cur_end,
            "category_id = ? AND id NOT IN (SELECT adjust_expense_id FROM balance_checks WHERE adjust_expense_id IS NOT NULL)",
            (c["id"],),
        )

        # Сравнение с прошлым месяцем строго день-в-день
        spent_prev = sum_in_range_byn(
            "budget_entries", "date", prev_start, prev_end_d,
            "category_id = ? AND id NOT IN (SELECT adjust_expense_id FROM balance_checks WHERE adjust_expense_id IS NOT NULL)",
            (c["id"],),
        )

        total_cur += spent_cur
        total_prev += spent_prev

        diff = round(spent_cur - spent_prev, 2)
        if spent_prev > 0.005:
            pct_change = round((diff / spent_prev) * 100, 1)
        elif spent_cur > 0.005:
            pct_change = 100.0
        else:
            pct_change = 0.0

        categories_data.append({
            "id": c["id"],
            "name": c["name"],
            "is_fixed": c.get("is_fixed", 0),
            "spent_current": round(spent_cur, 2),
            "spent_previous": round(spent_prev, 2),
            "diff": diff,
            "pct_change": pct_change,
        })

    # C5: Фильтрация для Парето (по умолчанию без фиксированных трат)
    pareto_candidates = [c for c in categories_data if (include_fixed or c["is_fixed"] == 0)]
    pareto_candidates.sort(key=lambda x: x["spent_current"], reverse=True)
    total_pareto = sum(c["spent_current"] for c in pareto_candidates)

    running_sum = 0.0
    pareto_core = []
    for c in pareto_candidates:
        c_spent = c["spent_current"]
        share = round((c_spent / total_pareto * 100), 1) if total_pareto > 0 else 0.0
        prev_running = running_sum
        running_sum += c_spent
        cum_pct = round((running_sum / total_pareto * 100), 1) if total_pareto > 0 else 0.0
        c["share"] = share
        c["cum_pct"] = cum_pct

        # Ядро — минимальный набор категорий, накопленная доля которого >= 80% (включая пересёкшую порог)
        if c_spent > 0 and (prev_running / total_pareto * 100 < 80.0 if total_pareto > 0 else False):
            pareto_core.append(c["name"])
            c["is_core"] = True
        else:
            c["is_core"] = False

    few_categories = len(pareto_candidates) < 5

    # C6: Топ роста и топ экономии (фильтр: обе суммы >= 20 BYN или изменение >= 10%)
    eligible_shifts = []
    for c in categories_data:
        if c["spent_current"] >= 20.0 or c["spent_previous"] >= 20.0 or abs(c["pct_change"]) >= 10.0:
            if abs(c["diff"]) > 0.005:
                eligible_shifts.append(c)

    top_risers = sorted([c for c in eligible_shifts if c["diff"] > 0], key=lambda x: x["diff"], reverse=True)[:3]
    top_savers = sorted([c for c in eligible_shifts if c["diff"] < 0], key=lambda x: x["diff"])[:3]

    return {
        "categories": pareto_candidates,
        "all_categories": categories_data,
        "total_current": round(total_cur, 2),
        "total_previous": round(total_prev, 2),
        "total_diff": round(total_cur - total_prev, 2),
        "top_risers": top_risers,
        "top_savers": top_savers,
        "pareto_core": pareto_core,
        "few_categories": few_categories,
        "comparison_day": d_prev,
    }


def goals_analytics(ref: Optional[date] = None) -> list[dict]:
    """
    Аналитика и честный прогноз темпа достижения целей накоплений (C7, A1).
    Все расчеты ведутся в валюте цели по курсам операций.
    """
    ref = ref or date.today()
    with get_db() as conn:
        goals = rows_to_dicts(conn.execute("SELECT * FROM savings_goals ORDER BY name").fetchall())

    result = []
    for g in goals:
        cur = normalize_currency(g.get("currency"))
        target_native = float(g.get("target_amount") or 0.0)
        current_saved = goal_balance(g["id"], cur)

        with get_db() as conn:
            entries = conn.execute(
                """
                SELECT amount, currency, kind, date, rate_usd, rate_eur, amount_byn
                FROM savings_entries
                WHERE goal_id = ?
                ORDER BY date ASC, id ASC
                """,
                (g["id"],),
            ).fetchall()

        if not entries:
            window_days = 0
            pace = None
        else:
            first_entry_d = parse_date(entries[0]["date"]) or ref
            days_since_first = max(1, (ref - first_entry_d).days + 1)
            window_days = min(90, days_since_first)

            if window_days < 14:
                pace = None
            else:
                window_start = ref - timedelta(days=window_days - 1)
                window_start_str = to_iso(window_start)
                
                # Чистое пополнение за окно в валюте цели
                net_window_cur = 0.0
                for e in entries:
                    if e["date"] >= window_start_str:
                        amt_cur = convert_at_entry(dict(e), cur)
                        k = e["kind"] or "deposit"
                        if k == "deposit":
                            net_window_cur += amt_cur
                        elif k in ("withdraw_free", "withdraw_spent"):
                            net_window_cur -= amt_cur

                months_in_window = window_days / 30.4375
                pace = round(net_window_cur / months_in_window, 2)

        remaining = max(0.0, round(target_native - current_saved, 2))
        pct = round((current_saved / target_native * 100), 1) if target_native > 0 else 100.0

        deadline_str = g.get("deadline")
        required_monthly = None
        deadline_status = "none"

        if target_native > 0 and current_saved >= target_native - 0.005:
            deadline_status = "reached"
            eta_date_str = "Достигнуто!"
        else:
            if deadline_str:
                dl_date = parse_date(deadline_str)
                if dl_date:
                    if dl_date < ref:
                        deadline_status = "overdue"
                    else:
                        months_left = max(0.1, (dl_date - ref).days / 30.4375)
                        required_monthly = round(remaining / months_left, 2)
                        if pace is not None:
                            deadline_status = "on_track" if pace >= required_monthly - 0.005 else "behind"
                        else:
                            deadline_status = "unknown"

            # ETA расчет
            if pace is not None and pace > 0.005 and remaining > 0:
                months_needed = remaining / pace
                eta_days = int(round(months_needed * 30.4375))
                eta_d = ref + timedelta(days=eta_days)
                eta_date_str = month_label(eta_d)
            elif pace is not None and pace <= 0.005:
                eta_date_str = "При текущем темпе: недостижимо"
            else:
                eta_date_str = "Мало данных"

        result.append({
            "id": g["id"],
            "name": g["name"],
            "type": g["type"],
            "target": target_native,
            "target_currency": cur,
            "saved_native": current_saved,
            "saved_byn": to_byn(current_saved, cur),
            "remaining": remaining,
            "pct": pct,
            "monthly_pace": pace,
            "required_monthly": required_monthly,
            "eta_date": eta_date_str,
            "deadline": deadline_str,
            "deadline_status": deadline_status,
        })
    return result


def six_months_trends(ref: Optional[date] = None) -> dict:
    """
    Тренды за 6 месяцев (C9):
    - Текущий неполный месяц помечается как 'в процессе' и ИСКЛЮЧАЕТСЯ из средних.
    - Средние считаются строго по закрытым месяцам, где есть данные.
    """
    ref = ref or date.today()
    months = last_n_months(6, ref)

    labels = []
    income_series = []
    expense_series = []
    savings_series = []
    net_flow_series = []
    cash_flow_series = []
    is_current_series = []

    closed_income = []
    closed_expense = []
    closed_savings = []
    closed_cash_flow = []

    first_entry_d = get_first_entry_date()

    for idx, (m_start, m_end) in enumerate(months):
        is_cur = (idx == len(months) - 1)
        labels.append(month_label(m_start))
        is_current_series.append(is_cur)

        m = get_period_metrics(m_start, m_end)

        income_series.append(m.inc)
        expense_series.append(m.exp_all)
        savings_series.append(m.net_save)
        net_flow_series.append(round(m.inc - m.exp_all, 2))
        cash_flow_series.append(m.cash_flow)

        # В средние закрытых месяцев включаем только закрытые месяцы, где уже существовали записи
        if not is_cur:
            if first_entry_d and m_end >= first_entry_d:
                closed_income.append(m.inc)
                closed_expense.append(m.exp_all)
                closed_savings.append(m.net_save)
                closed_cash_flow.append(m.cash_flow)

    count_closed = max(1, len(closed_income))
    avg_inc = round(sum(closed_income) / count_closed, 2) if closed_income else 0.0
    avg_exp = round(sum(closed_expense) / count_closed, 2) if closed_expense else 0.0
    avg_sav = round(sum(closed_savings) / count_closed, 2) if closed_savings else 0.0
    total_six_months_flow = round(sum(closed_cash_flow), 2) if closed_cash_flow else 0.0

    return {
        "labels": labels,
        "income": income_series,
        "expense": expense_series,
        "savings": savings_series,
        "net_flow": net_flow_series,
        "cash_flow": cash_flow_series,
        "is_current": is_current_series,
        "summary": {
            "avg_income": avg_inc,
            "avg_expense": avg_exp,
            "avg_savings": avg_sav,
            "total_free": total_six_months_flow,
            "total_flow_6m": total_six_months_flow,
            "closed_months_count": len(closed_income),
        },
    }


def generate_smart_insights(ref: Optional[date] = None) -> list[dict]:
    """Генерация умных правил и инсайтов."""
    ref = ref or date.today()
    start, end = period_bounds("month", ref)
    metrics = health_metrics(start, end, ref)
    shifts = category_comparison_and_pareto(ref)

    insights = []

    # 1. Сбережения
    if metrics["savings_rate"] is not None:
        if metrics["savings_rate"] >= 20:
            insights.append({
                "type": "success",
                "title": f"Норма сбережений: {metrics['savings_rate']}%",
                "message": "Отличный темп накоплений! Вы откладываете более 20% доходов.",
                "icon": "trending-up",
            })
        elif metrics["savings_rate"] < 10:
            insights.append({
                "type": "warning",
                "title": f"Низкая норма сбережений: {metrics['savings_rate']}%",
                "message": "В копилки уходит менее 10% дохода. Рекомендуется оптимизировать переменные расходы.",
                "icon": "alert-circle",
                "link": "/savings",
                "link_text": "В копилки",
            })

    # 2. Подушка безопасности
    if metrics["runway_months"] is not None:
        if metrics["runway_months"] < 1:
            insights.append({
                "type": "danger",
                "title": "Критичный резерв",
                "message": f"Подушки безопасности хватит всего на {metrics['runway_months']} мес. Рекомендуется довести резерв минимум до 3 месяцев.",
                "icon": "shield-alert",
                "link": "/savings",
                "link_text": "Пополнить резерв",
            })
        elif metrics["runway_months"] >= 6:
            insights.append({
                "type": "success",
                "title": "Финансовая крепость",
                "message": f"Ваш резерв покрывает {metrics['runway_months']} мес. текущих трат. Высокая степень финансовой независимости.",
                "icon": "shield-check",
            })

    # 3. Топ роста трат
    if shifts["top_risers"]:
        r = shifts["top_risers"][0]
        insights.append({
            "type": "info",
            "title": f"Всплеск: {r['name']}",
            "message": f"Траты выросли на {r['diff']:.2f} BYN (+{r['pct_change']}%) по сравнению с тем же днем прошлого месяца.",
            "icon": "arrow-up-right",
            "link": "/budget",
            "link_text": "Конверты",
        })

    return insights


def generate_ai_review(ref: Optional[date] = None) -> dict:
    """
    ИИ-аудит (Этап G):
    - Снимок для ИИ содержит ТОЛЬКО числа из metrics_core (SR, Surplus, R, Adh, BurnVar, SafePerDay, Forecast, Точность, CashFlow, цели).
    - Не отправляет имена людей из долгов и приватные комментарии.
    - Промпт строго запрещает пересчитывать числа.
    - Эвристический фолбэк при отсутствии API-ключа.
    """
    import os
    ref = ref or date.today()
    start_m, end_m = period_bounds("month", ref)

    m = get_period_metrics(start_m, end_m)
    metrics = health_metrics(start_m, end_m, ref)
    shifts = category_comparison_and_pareto(ref)
    goals = goals_analytics(ref)
    insights = generate_smart_insights(ref)

    api_key = (
        os.environ.get("GROQ_API_KEY", "").strip()
        or os.environ.get("AI_API_KEY", "").strip()
        or get_setting("ai_api_key", "").strip()
    )
    base_url = (
        os.environ.get("AI_BASE_URL", "").strip()
        or get_setting("ai_base_url", "").strip()
    )
    custom_model = (
        os.environ.get("AI_MODEL", "").strip()
        or get_setting("ai_model", "").strip()
    )

    data_snapshot = {
        "savings_rate_pct": metrics["savings_rate"],
        "surplus_pct": metrics["surplus_rate"],
        "runway_months": metrics["runway_months"],
        "runway_status": metrics["runway_label"],
        "budget_adherence_pct": metrics["adherence_pct"],
        "burn_var_daily_byn": metrics["daily_burn"],
        "safe_per_day_byn": metrics["safe_per_day"],
        "forecast_month_byn": metrics["forecast_month"],
        "accuracy_pct": metrics["accuracy_pct"],
        "unexplained_byn": metrics["unexplained_byn"],
        "cash_flow_month_byn": m.cash_flow,
        "pareto_core": shifts["pareto_core"][:3],
        "top_risers": [f"{r['name']} (+{r['diff']} BYN)" for r in shifts["top_risers"][:2]],
        "top_savers": [f"{s['name']} ({s['diff']} BYN)" for s in shifts["top_savers"][:2]],
        "goals_summary": [
            f"{g['name']}: {g['pct']}%, темп ~{g['monthly_pace']} {g['target_currency']}/мес, ETA: {g['eta_date']}"
            for g in goals[:3]
        ],
    }

    is_live = False
    llm_text = None
    error_hint = None
    active_model_name = "AI"

    if api_key:
        import urllib.request
        import urllib.error

        # Определение эндпоинта и модели
        if base_url:
            endpoint = base_url.rstrip("/")
            if not endpoint.endswith("/chat/completions"):
                endpoint += "/chat/completions"
            active_model_name = custom_model or ("deepseek-chat" if "deepseek" in endpoint else "llama-3.3-70b-versatile")
        elif api_key.startswith("gsk_"):
            endpoint = "https://api.groq.com/openai/v1/chat/completions"
            active_model_name = custom_model or "llama-3.3-70b-versatile"
        elif api_key.startswith("sk-or-"):
            endpoint = "https://openrouter.ai/api/v1/chat/completions"
            active_model_name = custom_model or "meta-llama/llama-3.2-3b-instruct:free"
        elif api_key.startswith("sk-"):
            # DeepSeek или OpenAI совместимый сервис
            endpoint = "https://api.deepseek.com/v1/chat/completions"
            active_model_name = custom_model or "deepseek-chat"
        else:
            endpoint = "https://api.groq.com/openai/v1/chat/completions"
            active_model_name = custom_model or "llama-3.3-70b-versatile"

        prompt = (
            "Ты — строгий финансовый аналитик системы AkselMoney. Проанализируй агрегированные показатели:\n"
            f"{json.dumps(data_snapshot, ensure_ascii=False, indent=2)}\n\n"
            "ПРАВИЛА:\n"
            "1. Используй ТОЛЬКО переданные числа, ничего не пересчитывай.\n"
            "2. Если показатель равен null, не выдумывай его, укажи что данных недостаточно.\n"
            "3. Структура ответа (3 лаконичных блока):\n"
            "   - **Главный финансовый вывод** (1-2 емких предложения о профиците/дефиците и норме сбережений).\n"
            "   - **Ключевые точки риска** (перерасход по темпу, сдвиги трат или недостаточный резерв).\n"
            "   - **Конкретные рекомендации** (2-3 четких шага на ближайшие 2 недели).\n"
            "Форматируй ответ аккуратным Markdown с маркерами."
        )

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "AkselMoney/1.0 (Linux; x86_64)",
        }
        if "openrouter" in endpoint:
            headers["HTTP-Referer"] = "https://akselmoney.local"
            headers["X-Title"] = "AkselMoney"

        try:
            req_data = json.dumps({
                "model": active_model_name,
                "messages": [
                    {"role": "system", "content": "Ты персональный финансовый аудитор. Будь объективен, строг и точен."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 600,
            }).encode("utf-8")

            req = urllib.request.Request(
                endpoint,
                data=req_data,
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=14) as response:
                resp_json = json.loads(response.read().decode("utf-8"))
                llm_text = resp_json["choices"][0]["message"]["content"]
                is_live = True
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8")
            except Exception:
                pass
            if e.code == 403:
                error_hint = "403 Forbidden: Сервис блокирует прямой доступ с IP сервера (типично для Groq из РФ/РБ без прокси). Укажите прокси в Base URL в Настройках или используйте DeepSeek API."
            elif e.code == 401:
                error_hint = "401 Unauthorized: Неверный или отозванный API-ключ. Проверьте правильность в Настройках."
            elif e.code == 404:
                error_hint = f"404 Not Found: Модель '{active_model_name}' не найдена у провайдера."
            else:
                error_hint = f"Ошибка API ({e.code}): {err_body[:100]}"
            llm_text = None
        except Exception as e:
            error_hint = f"Сетевая ошибка обращения к ИИ: {e}"
            llm_text = None

    if not llm_text:
        # Эвристический детерминированный фолбэк
        sr_desc = f"{metrics['savings_rate']}%" if metrics["savings_rate"] is not None else "недостаточно данных"
        rw_desc = f"{metrics['runway_months']} мес." if metrics["runway_months"] is not None else "резерв не задан"
        safe_desc = f"{metrics['safe_per_day']:.2f} BYN/день"
        cf_desc = f"{m.cash_flow:.2f} BYN"

        llm_text = (
            f"### Сводный аудит за {month_label(start_m)}\n\n"
            f"**Ключевой баланс:** Чистый денежный поток месяца составляет **{cf_desc}**, "
            f"норма сбережений зафиксирована на уровне **{sr_desc}**.\n\n"
            f"**Контроль лимитов и темпа:**\n"
            f"- Допустимый переменный расход: **{safe_desc}**.\n"
            f"- Подушка безопасности (Runway): **{rw_desc}** ({metrics['runway_label']}).\n"
            f"- Точность финансового учёта: **{metrics['accuracy_pct'] or '100'}%**.\n\n"
            f"**Фокус внимания:** Контролируйте ядро расходов ({', '.join(shifts['pareto_core'][:2]) or 'переменные траты'}) "
            f"и удерживайте дневной расход в рамках безопасного коридора."
        )

    return {
        "text": llm_text,
        "is_ai_live": is_live,
        "model": active_model_name if is_live else ("Ошибка API" if error_hint else "Эвристический аудит"),
        "error_hint": error_hint,
        "insights": insights,
        "metrics": metrics,
    }
