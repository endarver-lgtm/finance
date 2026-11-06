from datetime import date, timedelta
from calendar import monthrange
import json
import urllib.request
import urllib.error

from db import get_db, rows_to_dicts, get_setting
from services.constants import ONE_TIME_INCOME_LABEL
from services.currency import to_byn
from services.dates import add_months, last_n_months, month_label, month_start, period_bounds, to_iso
from services.planning import category_planned_for_period
from services.repository import sum_in_range_byn


def income_fact(start: date, end: date) -> float:
    return sum_in_range_byn("income_entries", "date", start, end)


def budget_fact(start: date, end: date) -> float:
    return budget_fact_own(start, end)


def budget_fact_own(start: date, end: date) -> float:
    """Собственные расходы (без трат из копилок)."""
    return sum_in_range_byn(
        "budget_entries", "date", start, end, "from_goal_id IS NULL"
    )


def budget_fact_from_goals(start: date, end: date) -> float:
    """Расходы, оплаченные из копилок."""
    return sum_in_range_byn(
        "budget_entries", "date", start, end, "from_goal_id IS NOT NULL"
    )


def savings_deposits_for_period(start: date, end: date) -> float:
    """Взносы в копилки за период."""
    return sum_in_range_byn(
        "savings_entries", "date", start, end, "kind = 'deposit'"
    )


def savings_withdraw_free_for_period(start: date, end: date) -> float:
    """Возврат из копилок в свободные средства за период."""
    return sum_in_range_byn(
        "savings_entries", "date", start, end, "kind = 'withdraw_free'"
    )


def free_cash_flow(start: date, end: date) -> float:
    """Свободный остаток: Приход - Собственные_расходы - Взносы + Возврат_в_свободные - Delta B."""
    from services.debts import delta_b

    inc = income_fact(start, end)
    own_exp = budget_fact_own(start, end)
    dep = savings_deposits_for_period(start, end)
    w_free = savings_withdraw_free_for_period(start, end)
    db = delta_b(start, end)

    return round(inc - own_exp - dep + w_free - db, 2)


def savings_total() -> float:
    with get_db() as conn:
        rows = conn.execute("SELECT amount, currency, kind FROM savings_entries").fetchall()
    total = 0.0
    for r in rows:
        kind = r["kind"] if "kind" in r.keys() and r["kind"] else "deposit"
        amt = to_byn(r["amount"], r["currency"] if "currency" in r.keys() else "BYN")
        if kind == "deposit":
            total += amt
        elif kind in ("withdraw_spent", "withdraw_free"):
            total -= amt
    return round(max(0.0, total), 2)




def expenses_by_category(start: date, end: date):
    with get_db() as conn:
        cats = rows_to_dicts(
            conn.execute("SELECT id, name FROM budget_categories").fetchall()
        )
    result = []
    for c in cats:
        spent = sum_in_range_byn(
            "budget_entries",
            "date",
            start,
            end,
            "category_id = ?",
            (c["id"],),
        )
        result.append({"id": c["id"], "name": c["name"], "spent": spent})
    result.sort(key=lambda x: (-x["spent"], x["name"]))
    return result


def income_by_months(months):
    labels, plan, fact = [], [], []
    with get_db() as conn:
        sources = conn.execute(
            """
            SELECT id, planned_amount, currency, frequency
            FROM income_sources WHERE active = 1
            """
        ).fetchall()
        received_by_source: dict[int, float] = {}
        for row in conn.execute(
            """
            SELECT source_id, amount, currency FROM income_entries
            WHERE source_id IS NOT NULL
            """
        ).fetchall():
            sid = row["source_id"]
            received_by_source[sid] = received_by_source.get(sid, 0.0) + to_byn(
                row["amount"], row["currency"]
            )
    for m_start, m_end in months:
        labels.append(month_label(m_start))
        p = 0.0
        for s in sources:
            amt = float(s["planned_amount"])
            cur = s["currency"] if "currency" in s.keys() else "BYN"
            planned_byn = to_byn(amt, cur)
            if s["frequency"] == "monthly":
                p += planned_byn
            elif s["frequency"] == "weekly":
                p += to_byn(amt * 4, cur)
            elif s["frequency"] == "one_time":
                received = received_by_source.get(s["id"], 0.0)
                if received < planned_byn - 0.005 and m_start <= date.today() <= m_end:
                    p += planned_byn
        plan.append(round(p, 2))
        fact.append(income_fact(m_start, m_end))
    return labels, plan, fact


def envelope_progress(period: str = "week", ref: date | None = None):
    start, end = period_bounds(period, ref)
    result = []
    with get_db() as conn:
        cats = rows_to_dicts(
            conn.execute(
                "SELECT * FROM budget_categories WHERE track_only = 0 ORDER BY name"
            ).fetchall()
        )
    for c in cats:
        planned_native = category_planned_for_period(c, period)
        cur = c.get("currency", "BYN")
        planned_byn = to_byn(planned_native, cur)
        spent = sum_in_range_byn(
            "budget_entries",
            "date",
            start,
            end,
            "category_id = ? AND from_goal_id IS NULL",
            (c["id"],),
        )
        result.append({
            "id": c["id"],
            "name": c["name"],
            "planned": planned_native,
            "planned_currency": cur,
            "planned_byn": planned_byn,
            "spent": spent,
            "remaining": max(0, planned_byn - spent),
            "pct": min(100, round(spent / planned_byn * 100, 1)) if planned_byn > 0 else 0,
        })
    return result



def upcoming_income(ref: date | None = None):
    ref = ref or date.today()
    start, end = period_bounds("month", ref)
    items = []
    with get_db() as conn:
        sources = rows_to_dicts(
            conn.execute(
                """
                SELECT * FROM income_sources
                WHERE active = 1 AND frequency != 'one_time'
                ORDER BY name
                """
            ).fetchall()
        )
        for s in sources:
            entries = conn.execute(
                """
                SELECT amount, currency FROM income_entries
                WHERE source_id = ? AND date >= ? AND date <= ?
                """,
                (s["id"], to_iso(start), to_iso(end)),
            ).fetchall()
            fact_byn = sum(to_byn(e["amount"], e["currency"]) for e in entries)
            cur = s.get("currency", "BYN")
            planned = float(s["planned_amount"])
            if s["frequency"] == "weekly":
                planned *= 4
            planned_byn = to_byn(planned, cur)
            items.append({
                "id": s["id"],
                "name": s["name"],
                "planned": planned,
                "planned_currency": cur,
                "fact": round(fact_byn, 2),
                "fact_currency": "BYN",
                "status": "received" if fact_byn >= planned_byn else "pending",
            })
    return items


def _date_filter_clause(col: str, date_from, date_to):
    parts, params = [], []
    if date_from:
        parts.append(f"{col} >= ?")
        params.append(to_iso(date_from))
    if date_to:
        parts.append(f"{col} <= ?")
        params.append(to_iso(date_to))
    return (" AND ".join(parts), params) if parts else ("1=1", [])


def history_rows(
    date_from: date | None,
    date_to: date | None,
    type_filter: str,
    category_filter: str,
):
    rows = []

    if type_filter in ("", "income"):
        clause, params = _date_filter_clause("e.date", date_from, date_to)
        with get_db() as conn:
            for r in conn.execute(
                f"""
                SELECT e.id, e.date, e.amount, e.currency, e.comment, e.source_id,
                       COALESCE(s.name, '{ONE_TIME_INCOME_LABEL}') AS label,
                       'income' AS kind
                FROM income_entries e
                LEFT JOIN income_sources s ON s.id = e.source_id
                WHERE {clause}
                ORDER BY e.date DESC
                """,
                params,
            ).fetchall():
                row = dict(r)
                if category_filter and row["label"] != category_filter:
                    continue
                rows.append(row)

    if type_filter in ("", "expense"):
        clause, params = _date_filter_clause("e.date", date_from, date_to)
        with get_db() as conn:
            for r in conn.execute(
                f"""
                SELECT e.id, e.date, e.amount, e.currency, e.comment, e.category_id,
                       c.name AS label, 'expense' AS kind,
                       g.name AS from_goal_name
                FROM budget_entries e
                JOIN budget_categories c ON c.id = e.category_id
                LEFT JOIN savings_goals g ON g.id = e.from_goal_id
                WHERE {clause}
                ORDER BY e.date DESC
                """,
                params,
            ).fetchall():
                row = dict(r)
                if category_filter and row["label"] != category_filter:
                    continue
                rows.append(row)

    if type_filter in ("", "savings", "savings_withdraw"):
        clause, params = _date_filter_clause("e.date", date_from, date_to)
        with get_db() as conn:
            for r in conn.execute(
                f"""
                SELECT e.id, e.date, e.amount, e.currency, e.comment, e.goal_id,
                       g.name AS label, e.kind AS entry_kind
                FROM savings_entries e
                JOIN savings_goals g ON g.id = e.goal_id
                WHERE {clause}
                ORDER BY e.date DESC
                """,
                params,
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
        clause, params = _date_filter_clause("d.date", date_from, date_to)
        with get_db() as conn:
            for r in conn.execute(
                f"""
                SELECT d.id, d.date, d.amount, d.currency, d.comment, d.person,
                       d.person AS label, 'debt' AS kind, d.kind AS debt_kind
                FROM debts d
                WHERE {clause}
                ORDER BY d.date DESC
                """,
                params,
            ).fetchall():
                row = dict(r)
                if category_filter and row["label"] != category_filter:
                    continue
                d_kind = row.get("debt_kind")
                row["sign"] = "+" if d_kind in ("i_paid", "repay_to_him") else "−"
                rows.append(row)

    rows.sort(key=lambda x: x["date"], reverse=True)
    return rows


# ==============================================================================
# Comprehensive Financial Analysis & Intelligence Engine
# ==============================================================================

def health_metrics(start: date, end: date, ref: date | None = None) -> dict:
    """Расчёт интегральных метрик финансового здоровья."""
    ref = ref or date.today()
    inc = income_fact(start, end)
    own_exp = budget_fact_own(start, end)
    dep = savings_deposits_for_period(start, end)
    w_free = savings_withdraw_free_for_period(start, end)
    net_saved = max(0.0, dep - w_free)

    # 1. Savings Rate (Норма сбережений)
    if inc > 0:
        savings_rate = round((net_saved / inc) * 100, 1)
    else:
        savings_rate = 0.0

    if savings_rate >= 20.0:
        sr_status, sr_label = "ok", "Отлично (>=20%)"
    elif savings_rate >= 10.0:
        sr_status, sr_label = "warning", "Нормально (10–20%)"
    else:
        sr_status, sr_label = "danger", "Низкая (<10%)"

    # 2. Runway (Подушка безопасности в месяцах)
    total_savings = savings_total()
    # Средний месячный расход за последние 90 дней
    past_90_start = ref - timedelta(days=90)
    past_exp = budget_fact_own(past_90_start, ref)
    if past_exp > 0.01:
        avg_monthly_exp = past_exp / 3.0
    elif own_exp > 0.01:
        avg_monthly_exp = own_exp
    else:
        avg_monthly_exp = 1.0

    if total_savings > 0 and avg_monthly_exp > 0:
        runway_months = round(total_savings / avg_monthly_exp, 1)
    elif total_savings > 0:
        runway_months = 99.0
    else:
        runway_months = 0.0

    if runway_months >= 6.0:
        rw_status, rw_label = "stellar", "Капитал (>=6 мес.)"
    elif runway_months >= 3.0:
        rw_status, rw_label = "ok", "Надёжно (3–6 мес.)"
    elif runway_months >= 1.0:
        rw_status, rw_label = "warning", "Минимум (1–3 мес.)"
    else:
        rw_status, rw_label = "danger", "Критично (<1 мес.)"

    # 3. Budget Adherence (Дисциплина конвертов)
    envelopes = envelope_progress("month", ref)
    total_env = len(envelopes)
    in_limit_count = sum(1 for e in envelopes if e["spent"] <= e["planned_byn"] or e["planned_byn"] == 0)
    adherence_pct = round((in_limit_count / total_env * 100), 1) if total_env > 0 else 100.0

    if adherence_pct >= 80.0:
        adh_status = "ok"
    elif adherence_pct >= 60.0:
        adh_status = "warning"
    else:
        adh_status = "danger"

    # 4. Burn Rate (Средний расход в день)
    days_count = max(1, (end - start).days + 1)
    daily_burn = round(own_exp / days_count, 2)

    return {
        "savings_rate": savings_rate,
        "savings_rate_status": sr_status,
        "savings_rate_label": sr_label,
        "runway_months": runway_months,
        "runway_status": rw_status,
        "runway_label": rw_label,
        "adherence_pct": adherence_pct,
        "adherence_status": adh_status,
        "in_limit_count": in_limit_count,
        "total_envelopes": total_env,
        "daily_burn": daily_burn,
        "total_savings": total_savings,
        "avg_monthly_exp": round(avg_monthly_exp, 2),
    }


def cash_flow_waterfall(start: date, end: date) -> dict:
    """Данные для водопада денежного потока (Cash Flow Waterfall)."""
    from services.debts import delta_b

    inc = income_fact(start, end)
    exp = budget_fact_own(start, end)
    dep = savings_deposits_for_period(start, end)
    w_free = savings_withdraw_free_for_period(start, end)
    net_savings = round(dep - w_free, 2)
    db = delta_b(start, end)
    free = free_cash_flow(start, end)

    steps = [
        {"label": "Доходы", "amount": inc, "type": "positive", "desc": "Все фактические поступления"},
        {"label": "Расходы", "amount": -exp, "type": "negative", "desc": "Собственные текущие траты"},
        {"label": "Копилки", "amount": -net_savings, "type": "negative" if net_savings >= 0 else "positive", "desc": "Чистое пополнение копилок"},
    ]
    if abs(db) > 0.005:
        steps.append({
            "label": "Долги (Δ)",
            "amount": -db,
            "type": "negative" if db > 0 else "positive",
            "desc": "Изменение баланса долгов за период",
        })
    steps.append({
        "label": "Свободный кэш",
        "amount": free,
        "type": "total",
        "desc": "Чистый остаток средств",
    })

    return {
        "income": inc,
        "expenses": exp,
        "savings": net_savings,
        "debt_delta": db,
        "free_cash": free,
        "steps": steps,
    }


def six_months_trends(ref: date | None = None) -> dict:
    """Глубокая динамика за последние 6 месяцев."""
    from services.debts import delta_b

    ref = ref or date.today()
    months = last_n_months(6, ref)

    labels = []
    income_series = []
    expense_series = []
    savings_series = []
    free_series = []
    net_flow_series = []

    for m_start, m_end in months:
        labels.append(month_label(m_start))
        inc = income_fact(m_start, m_end)
        exp = budget_fact_own(m_start, m_end)
        dep = savings_deposits_for_period(m_start, m_end)
        wf = savings_withdraw_free_for_period(m_start, m_end)
        sav = round(dep - wf, 2)
        fr = free_cash_flow(m_start, m_end)

        income_series.append(round(inc, 2))
        expense_series.append(round(exp, 2))
        savings_series.append(round(sav, 2))
        free_series.append(round(fr, 2))
        net_flow_series.append(round(inc - exp, 2))

    tot_inc = round(sum(income_series), 2)
    tot_exp = round(sum(expense_series), 2)
    tot_sav = round(sum(savings_series), 2)
    tot_free = round(sum(free_series), 2)

    count_m = max(1, len(months))
    avg_inc = round(tot_inc / count_m, 2)
    avg_exp = round(tot_exp / count_m, 2)
    avg_sav = round(tot_sav / count_m, 2)
    avg_free = round(tot_free / count_m, 2)

    overall_sr = round((tot_sav / tot_inc * 100), 1) if tot_inc > 0 else 0.0

    return {
        "labels": labels,
        "income": income_series,
        "expense": expense_series,
        "savings": savings_series,
        "free_cash": free_series,
        "net_flow": net_flow_series,
        "summary": {
            "total_income": tot_inc,
            "total_expense": tot_exp,
            "total_savings": tot_sav,
            "total_free": tot_free,
            "avg_income": avg_inc,
            "avg_expense": avg_exp,
            "avg_savings": avg_sav,
            "avg_free": avg_free,
            "overall_savings_rate": overall_sr,
        },
    }


def category_comparison_and_pareto(ref: date | None = None) -> dict:
    """Сравнение категорий расходов текущего и прошлого месяцев + анализ Парето."""
    ref = ref or date.today()
    cur_start, cur_end = period_bounds("month", ref)

    prev_month_ref = add_months(cur_start, -1)
    prev_start, prev_end = period_bounds("month", prev_month_ref)

    with get_db() as conn:
        cats = rows_to_dicts(
            conn.execute("SELECT id, name FROM budget_categories ORDER BY name").fetchall()
        )

    categories_data = []
    total_cur = 0.0
    total_prev = 0.0

    for c in cats:
        spent_cur = sum_in_range_byn(
            "budget_entries", "date", cur_start, cur_end,
            "category_id = ? AND from_goal_id IS NULL", (c["id"],)
        )
        spent_prev = sum_in_range_byn(
            "budget_entries", "date", prev_start, prev_end,
            "category_id = ? AND from_goal_id IS NULL", (c["id"],)
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
            "spent_current": round(spent_cur, 2),
            "spent_previous": round(spent_prev, 2),
            "diff": diff,
            "pct_change": pct_change,
        })

    # Сортировка по тратам текущего месяца для Парето
    categories_data.sort(key=lambda x: x["spent_current"], reverse=True)

    running_sum = 0.0
    pareto_core = []
    for c in categories_data:
        share = round((c["spent_current"] / total_cur * 100), 1) if total_cur > 0 else 0.0
        running_sum += c["spent_current"]
        cum_pct = round((running_sum / total_cur * 100), 1) if total_cur > 0 else 0.0
        c["share"] = share
        c["cum_pct"] = cum_pct
        if c["spent_current"] > 0 and (cum_pct <= 80.0 or len(pareto_core) < 2):
            pareto_core.append(c["name"])

    # Топ роста и топ экономии
    sorted_by_growth = sorted(categories_data, key=lambda x: x["diff"], reverse=True)
    top_risers = [c for c in sorted_by_growth if c["diff"] > 0][:3]
    top_savers = [c for c in sorted(categories_data, key=lambda x: x["diff"]) if c["diff"] < 0][:3]

    return {
        "categories": categories_data,
        "total_current": round(total_cur, 2),
        "total_previous": round(total_prev, 2),
        "total_diff": round(total_cur - total_prev, 2),
        "total_pct_change": round(((total_cur - total_prev) / total_prev * 100), 1) if total_prev > 0 else 0.0,
        "top_risers": top_risers,
        "top_savers": top_savers,
        "pareto_core": pareto_core,
    }


def goals_analytics(ref: date | None = None) -> list[dict]:
    """Аналитика и прогноз достижения целей накоплений (ETA)."""
    ref = ref or date.today()
    with get_db() as conn:
        goals = rows_to_dicts(conn.execute("SELECT * FROM savings_goals ORDER BY name").fetchall())

    result = []
    months_3_ago = add_months(month_start(ref), -3)

    for g in goals:
        cur = g.get("currency", "BYN")
        target_native = float(g.get("target_amount") or 0.0)
        target_byn = to_byn(target_native, cur)

        with get_db() as conn:
            entries = conn.execute(
                "SELECT amount, currency, kind, date FROM savings_entries WHERE goal_id = ?",
                (g["id"],)
            ).fetchall()

        saved_byn = 0.0
        recent_deposits_3m = 0.0

        for e in entries:
            amt_byn = to_byn(e["amount"], e["currency"])
            kind = e["kind"] or "deposit"
            if kind == "deposit":
                saved_byn += amt_byn
                # Считаем взносы за последние 3 месяца
                if e["date"] >= to_iso(months_3_ago):
                    recent_deposits_3m += amt_byn
            else:
                saved_byn -= amt_byn
                if e["date"] >= to_iso(months_3_ago):
                    recent_deposits_3m -= amt_byn

        saved_byn = max(0.0, round(saved_byn, 2))
        remaining = max(0.0, round(target_byn - saved_byn, 2))
        pct = min(100.0, round((saved_byn / target_byn * 100), 1)) if target_byn > 0 else 100.0

        # Средний темп в месяц
        monthly_pace = max(0.0, round(recent_deposits_3m / 3.0, 2))

        eta_months = None
        eta_date_str = None
        deadline_status = "none"

        if target_byn > 0 and remaining > 0:
            if monthly_pace > 0.01:
                eta_months = round(remaining / monthly_pace, 1)
                months_to_add = int(round(eta_months))
                est_date = add_months(ref, months_to_add)
                eta_date_str = month_label(est_date)
            else:
                eta_date_str = "При текущем темпе: неизвестно"

        deadline = g.get("deadline")
        if deadline:
            try:
                dl_date = date.fromisoformat(deadline)
                months_left_to_dl = (dl_date.year - ref.year) * 12 + (dl_date.month - ref.month)
                if remaining <= 0:
                    deadline_status = "completed"
                elif eta_months is not None and eta_months <= months_left_to_dl:
                    deadline_status = "on_track"
                else:
                    deadline_status = "behind"
            except Exception:
                deadline_status = "unknown"
        elif remaining <= 0 and target_byn > 0:
            deadline_status = "completed"

        result.append({
            "id": g["id"],
            "name": g["name"],
            "type": g.get("type", "want"),
            "target": target_native,
            "target_currency": cur,
            "target_byn": target_byn,
            "saved_byn": saved_byn,
            "remaining_byn": remaining,
            "pct": pct,
            "monthly_pace": monthly_pace,
            "eta_months": eta_months,
            "eta_date": eta_date_str,
            "deadline": deadline,
            "deadline_status": deadline_status,
        })

    return result


def generate_smart_insights(ref: date | None = None) -> list[dict]:
    """Умный эвристический генератор инсайтов и рекомендаций на основе фин-анализа."""
    ref = ref or date.today()
    start_m, end_m = period_bounds("month", ref)

    metrics = health_metrics(start_m, end_m, ref)
    trends = six_months_trends(ref)
    shifts = category_comparison_and_pareto(ref)
    goals = goals_analytics(ref)
    cf = cash_flow_waterfall(start_m, end_m)

    insights = []

    # 1. Анализ свободного остатка
    if cf["free_cash"] < 0:
        insights.append({
            "type": "danger",
            "title": "Дефицит свободного остатка",
            "message": f"В текущем месяце расходы и сбережения превышают приход на {abs(cf['free_cash']):.2f} BYN. Рекомендуется временно сократить необязательные траты.",
            "icon": "alert-triangle",
            "link": "/budget",
            "link_text": "Оптимизировать бюджет",
        })
    elif cf["free_cash"] > 200:
        insights.append({
            "type": "success",
            "title": "Уверенный профицит средств",
            "message": f"Свободный остаток за месяц составляет +{cf['free_cash']:.2f} BYN. Отличная возможность пополнить финансовую подушку или приблизить крупную цель.",
            "icon": "trending-up",
            "link": "/savings",
            "link_text": "Отправить в копилку",
        })

    # 2. Норма сбережений (Savings Rate)
    sr = metrics["savings_rate"]
    if sr >= 20:
        insights.append({
            "type": "success",
            "title": f"Высокая норма сбережений: {sr}%",
            "message": "Вы сохраняете более пятой части всех доходов. Это признак высокой финансовой устойчивости.",
            "icon": "shield-check",
            "link": "/savings",
            "link_text": "Мои накопления",
        })
    elif sr < 10 and metrics["savings_rate_status"] == "danger":
        insights.append({
            "type": "warning",
            "title": f"Низкая доля сбережений: {sr}%",
            "message": "Менее 10% дохода направляется в капитал. Постарайтесь откладывать даже небольшую фиксированную сумму сразу в день прихода.",
            "icon": "pie-chart",
            "link": "/income",
            "link_text": "Источники доходов",
        })

    # 3. Резкие сдвиги в расходах
    if shifts["top_risers"]:
        worst = shifts["top_risers"][0]
        if worst["diff"] >= 20.0:
            insights.append({
                "type": "warning",
                "title": f"Скачок трат в категории «{worst['name']}»",
                "message": f"Расходы выросли на +{worst['diff']:.2f} BYN ({worst['pct_change']:+.1f}%) относительно прошлого месяца.",
                "icon": "arrow-up-right",
                "link": "/budget",
                "link_text": "Проверить траты",
            })

    # 4. Подушка безопасности (Runway)
    rw = metrics["runway_months"]
    if rw < 1.0:
        insights.append({
            "type": "danger",
            "title": "Резервный фонд меньше 1 месяца",
            "message": f"Текущих накоплений хватит лишь на {rw} мес. расходов. Приоритетная задача — сформировать фонд на 3–6 месяцев.",
            "icon": "umbrella",
            "link": "/savings",
            "link_text": "Создать цель «Резерв»",
        })
    elif rw >= 6.0:
        insights.append({
            "type": "stellar",
            "title": f"Мощный запас прочности: {rw} мес.",
            "message": "Подушка безопасности надежно перекрывает полугодовые расходы. Ваши базовые риски закрыты.",
            "icon": "award",
            "link": "/savings",
            "link_text": "Крупные цели",
        })

    # 5. Прогресс по целям
    near_goals = [g for g in goals if 80 <= g["pct"] < 100]
    if near_goals:
        target_g = near_goals[0]
        insights.append({
            "type": "info",
            "title": f"Цель «{target_g['name']}» близка к финишу ({target_g['pct']}%)",
            "message": f"Осталось накопить всего {target_g['remaining_byn']:.2f} BYN до закрытия цели!",
            "icon": "target",
            "link": "/savings",
            "link_text": "Пополнить и закрыть",
        })

    # Если инсайтов мало — добавим полезное наблюдение по дисциплине
    if len(insights) < 3 and metrics["adherence_pct"] >= 80:
        insights.append({
            "type": "success",
            "title": f"Дисциплина бюджета: {metrics['adherence_pct']}%",
            "message": f"{metrics['in_limit_count']} из {metrics['total_envelopes']} конвертов остаются в запланированных лимитах.",
            "icon": "check-circle",
            "link": "/budget",
            "link_text": "Обзор бюджета",
        })

    return insights[:4]


def format_ai_markdown(text: str) -> str:
    """Преобразует базовую markdown-разметку от LLM в безопасный стилизованный HTML."""
    import re
    # Заголовки ### и ##
    res = re.sub(r'###\s+(.+)', r'<h4 class="ai-heading">\1</h4>', text)
    res = re.sub(r'##\s+(.+)', r'<h3 class="ai-heading">\1</h3>', res)
    # Жирный шрифт **text**
    res = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', res)
    # Списки
    lines = res.split('\n')
    out_lines = []
    in_list = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(('- ', '* ', '• ')):
            if not in_list:
                out_lines.append('<ul class="ai-list">')
                in_list = True
            content = stripped[2:].strip()
            out_lines.append(f'<li>{content}</li>')
        else:
            if in_list:
                out_lines.append('</ul>')
                in_list = False
            if stripped:
                out_lines.append(f'<p>{line}</p>')
            else:
                out_lines.append('')
    if in_list:
        out_lines.append('</ul>')
    return '\n'.join(out_lines)


def generate_ai_review(ref: date | None = None) -> dict:
    """Генерация комплексного отчета: Groq (Qwen 3.8-27b) или локальный умный эвристический анализ."""
    import os
    ref = ref or date.today()
    start_m, end_m = period_bounds("month", ref)

    metrics = health_metrics(start_m, end_m, ref)
    trends = six_months_trends(ref)
    shifts = category_comparison_and_pareto(ref)
    cf = cash_flow_waterfall(start_m, end_m)
    insights = generate_smart_insights(ref)

    api_key = (
        get_setting("ai_api_key", "").strip()
        or os.environ.get("GROQ_API_KEY", "").strip()
        or os.environ.get("AI_API_KEY", "").strip()
    )
    ai_model = get_setting("ai_model", "").strip() or "qwen/qwen3.8-27b"
    ai_provider = get_setting("ai_provider", "").strip() or "groq"

    cur_month_name = month_label(start_m)
    pareto_str = ", ".join(shifts["pareto_core"][:3]) or "Не определено"

    llm_text = None
    is_live = False

    if api_key:
        sys_prompt = (
            "Ты — персональный финансовый консультант в приложении AkselMoney. "
            "Проанализируй финансовые показатели пользователя за текущий месяц и полугодовую динамику. "
            "Дай чёткое, ёмкое, структурированное заключение на русском языке (используй emoji, списки и жирный шрифт):\n"
            "1. 📊 Баланс месяца и кэшфлоу (оценка профицита/дефицита)\n"
            "2. ⚠️ Главные точки риска или скрытые утечки бюджета\n"
            "3. 🛡️ Подушка безопасности и темп накоплений\n"
            "4. 💡 2 конкретных практических шага на ближайшие 2–3 недели."
        )

        prompt_data = (
            f"Месяц: {cur_month_name}. "
            f"Доходы факт: {cf['income']:.2f} BYN, Расходы: {cf['expenses']:.2f} BYN, "
            f"Отложено в копилки: {cf['savings']:.2f} BYN, Свободный остаток: {cf['free_cash']:.2f} BYN. "
            f"Норма сбережений: {metrics['savings_rate']}%, Запас подушки: {metrics['runway_months']} мес. "
            f"(средний расход {metrics['avg_monthly_exp']:.2f} BYN/мес). "
            f"Дисциплина бюджета: {metrics['adherence_pct']}% ({metrics['in_limit_count']} из {metrics['total_envelopes']} в лимите). "
            f"Ядро расходов (80%): {pareto_str}. "
            f"Средний доход за 6 мес: {trends['summary']['avg_income']:.2f} BYN, расход: {trends['summary']['avg_expense']:.2f} BYN, "
            f"сбережения: {trends['summary']['avg_savings']:.2f} BYN."
        )

        try:
            # Groq API endpoint
            if api_key.startswith("gsk_") or ai_provider == "groq":
                endpoint = "https://api.groq.com/openai/v1/chat/completions"
                model_name = ai_model if "qwen" in ai_model or "llama" in ai_model else "qwen/qwen3.8-27b"
            else:
                endpoint = "https://openrouter.ai/api/v1/chat/completions"
                model_name = ai_model or "meta-llama/llama-3.2-3b-instruct:free"

            req_data = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": prompt_data}
                ],
                "max_tokens": 700,
                "temperature": 0.4,
            }
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(req_data).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0 AkselMoney/1.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                resp_json = json.loads(resp.read().decode("utf-8"))
                llm_raw = resp_json["choices"][0]["message"]["content"].strip()
                llm_text = format_ai_markdown(llm_raw)
                is_live = True
        except Exception as e:
            llm_text = None

    if not llm_text:
        # Автоматическая интеллектуальная сборка на основе правил
        bullets = []
        if cf["free_cash"] < 0:
            bullets.append(f"⚠️ **Дефицит месяца**: расходная часть превысила доходы на {abs(cf['free_cash']):.2f} BYN. Первостепенная мера — сократить траты в топ-статьях ({pareto_str}).")
        else:
            bullets.append(f"✅ **Положительный кэшфлоу**: чистый свободный остаток составляет +{cf['free_cash']:.2f} BYN.")

        if metrics["savings_rate"] >= 20:
            bullets.append(f"🟢 **Норма накоплений ({metrics['savings_rate']}%)** на здоровом уровне. Капитал планомерно увеличивается.")
        else:
            bullets.append(f"🟡 **Сбережения ({metrics['savings_rate']}%)**: рекомендуемый целевой ориентир — откладывать 15–20% каждого поступления.")

        if metrics["runway_months"] < 2.0:
            bullets.append(f"🔴 **Подушка безопасности ({metrics['runway_months']} мес.)**: уязвима к непредвиденным обстоятельствам. Направляйте свободный кэш в цель «Резерв».")
        else:
            bullets.append(f"🛡️ **Финансовый резерв**: накопленных средств хватит на {metrics['runway_months']} мес. автономной жизни.")

        raw = "\n\n".join(bullets)
        llm_text = format_ai_markdown(raw)

    return {
        "text": llm_text,
        "is_ai_live": is_live,
        "model": "Groq Qwen 3.8-27b" if is_live else "Встроенный аналитик",
        "insights": insights,
        "metrics": metrics,
    }


