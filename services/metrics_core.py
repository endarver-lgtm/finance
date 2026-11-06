from dataclasses import dataclass
from datetime import date
from typing import Optional

from db import get_db
from services.currency import to_byn
from services.dates import parse_date, to_iso
from services.debts import delta_b as calc_delta_b


@dataclass
class PeriodMetrics:
    adj_inc: float
    adj_exp: float
    adj_net: float
    inc: float
    exp_own: float
    exp_goal: float
    exp_all: float
    dep: float
    w_free: float
    w_spent: float
    net_save: float
    delta_b: float
    cash_flow: float
    exp_gross: float = 0.0
    total_offset: float = 0.0

    def to_dict(self) -> dict:
        return {
            "adj_inc": self.adj_inc,
            "adj_exp": self.adj_exp,
            "adj_net": self.adj_net,
            "inc": self.inc,
            "exp_own": self.exp_own,
            "exp_gross": self.exp_gross,
            "total_offset": self.total_offset,
            "exp_goal": self.exp_goal,
            "exp_all": self.exp_all,
            "dep": self.dep,
            "w_free": self.w_free,
            "w_spent": self.w_spent,
            "net_save": self.net_save,
            "delta_b": self.delta_b,
            "cash_flow": self.cash_flow,
        }


def get_first_entry_date() -> Optional[date]:
    """Возвращает самую раннюю дату записи в системе или None."""
    with get_db() as conn:
        d1 = conn.execute("SELECT MIN(date) FROM income_entries").fetchone()[0]
        d2 = conn.execute("SELECT MIN(date) FROM budget_entries").fetchone()[0]
        d3 = conn.execute("SELECT MIN(date) FROM savings_entries").fetchone()[0]
        d4 = conn.execute("SELECT MIN(date) FROM debts").fetchone()[0]
    
    dates = [parse_date(d) for d in (d1, d2, d3, d4) if d]
    valid = [d for d in dates if d is not None]
    return min(valid) if valid else None


def history_months(ref: Optional[date] = None, window_days: int = 90) -> Optional[float]:
    """
    Хелпер глубины истории (Этап B):
    Возвращает min(window_days, дней с первой записи пользователя) / 30.4375.
    Если дней меньше 14, возвращает None («мало данных»).
    """
    ref = ref or date.today()
    first_d = get_first_entry_date()
    if not first_d:
        return None
    
    days = (ref - first_d).days + 1
    if days < 14:
        return None
    
    effective_days = min(float(window_days), float(days))
    return round(effective_days / 30.4375, 4)


def get_period_metrics(start: date, end: date) -> PeriodMetrics:
    """
    Единая точка истины (Этап B) для всех финансовых потоков за период [start, end].
    Все суммы считаются в BYN по amount_byn (с fallback на to_byn).
    """
    start_str = to_iso(start)
    end_str = to_iso(end)

    with get_db() as conn:
        # Корректировки сверки
        adj_inc_ids_rows = conn.execute(
            "SELECT adjust_income_id FROM balance_checks WHERE adjust_income_id IS NOT NULL"
        ).fetchall()
        adj_inc_ids = {r[0] for r in adj_inc_ids_rows}

        adj_exp_ids_rows = conn.execute(
            "SELECT adjust_expense_id FROM balance_checks WHERE adjust_expense_id IS NOT NULL"
        ).fetchall()
        adj_exp_ids = {r[0] for r in adj_exp_ids_rows}

        # 1. Доходы
        inc_rows = conn.execute(
            "SELECT id, amount, currency, amount_byn FROM income_entries WHERE date >= ? AND date <= ?",
            (start_str, end_str),
        ).fetchall()

        adj_inc = 0.0
        inc = 0.0
        for r in inc_rows:
            val = float(r["amount_byn"]) if r["amount_byn"] is not None else to_byn(r["amount"], r["currency"])
            if r["id"] in adj_inc_ids:
                adj_inc += val
            else:
                inc += val

        # 2. Расходы
        exp_rows = conn.execute(
            "SELECT id, amount, currency, amount_byn, from_goal_id FROM budget_entries WHERE date >= ? AND date <= ?",
            (start_str, end_str),
        ).fetchall()

        adj_exp = 0.0
        exp_gross = 0.0
        exp_goal = 0.0
        for r in exp_rows:
            val = float(r["amount_byn"]) if r["amount_byn"] is not None else to_byn(r["amount"], r["currency"])
            if r["id"] in adj_exp_ids:
                adj_exp += val
            elif r["from_goal_id"] is not None:
                exp_goal += val
            else:
                exp_gross += val

        # J2: Зачёт долгов (Offset)
        offset_rows = conn.execute(
            """
            SELECT amount, currency, amount_byn
            FROM debts
            WHERE kind = 'i_paid'
              AND source = 'manual'
              AND category_id IS NOT NULL
              AND COALESCE(offset_date, date) >= ?
              AND COALESCE(offset_date, date) <= ?
            """,
            (start_str, end_str),
        ).fetchall()

        total_offset = sum(
            float(r["amount_byn"]) if r["amount_byn"] is not None else to_byn(r["amount"], r["currency"])
            for r in offset_rows
        )
        exp_own = exp_gross - total_offset

        # 3. Копилки
        sav_rows = conn.execute(
            "SELECT amount, currency, amount_byn, kind FROM savings_entries WHERE date >= ? AND date <= ?",
            (start_str, end_str),
        ).fetchall()

        dep = 0.0
        w_free = 0.0
        w_spent = 0.0
        for r in sav_rows:
            val = float(r["amount_byn"]) if r["amount_byn"] is not None else to_byn(r["amount"], r["currency"])
            k = r["kind"] or "deposit"
            if k == "deposit":
                dep += val
            elif k == "withdraw_free":
                w_free += val
            elif k == "withdraw_spent":
                w_spent += val

    # Долги
    db = calc_delta_b(start, end)

    # Округление компонентов до копеек
    adj_inc = round(adj_inc, 2)
    adj_exp = round(adj_exp, 2)
    adj_net = round(adj_inc - adj_exp, 2)
    inc = round(inc, 2)
    exp_gross = round(exp_gross, 2)
    total_offset = round(total_offset, 2)
    exp_own = round(exp_own, 2)
    exp_goal = round(exp_goal, 2)
    exp_all = round(exp_own + exp_goal, 2)
    dep = round(dep, 2)
    w_free = round(w_free, 2)
    w_spent = round(w_spent, 2)
    net_save = round(dep - w_free - w_spent, 2)

    # CashFlow = Inc − Exp_own − Dep + W_free − ΔB + Adj_net
    # Инвариант: CashFlow равен прежнему Free = (Inc + Adj_inc) - (Exp_own + Adj_exp) - Dep + W_free - ΔB
    cash_flow = round(inc - exp_own - dep + w_free - db + adj_net, 2)

    return PeriodMetrics(
        adj_inc=adj_inc,
        adj_exp=adj_exp,
        adj_net=adj_net,
        inc=inc,
        exp_own=exp_own,
        exp_goal=exp_goal,
        exp_all=exp_all,
        dep=dep,
        w_free=w_free,
        w_spent=w_spent,
        net_save=net_save,
        delta_b=db,
        cash_flow=cash_flow,
        exp_gross=exp_gross,
        total_offset=total_offset,
    )
