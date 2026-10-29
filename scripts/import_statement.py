import csv
import io
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from config import DATABASE_PATH
from db import get_db, now_iso


def import_csv_data(csv_text: str):
    f = io.StringIO(csv_text.strip())
    reader = csv.DictReader(f, delimiter=";")

    inserted_expenses = 0
    inserted_incomes = 0
    skipped = 0

    with get_db() as conn:
        # Load categories map: name -> id
        cat_rows = conn.execute("SELECT id, name FROM budget_categories").fetchall()
        cat_map = {r["name"].strip().lower(): r["id"] for r in cat_rows}

        # Load income sources map: name -> id
        inc_rows = conn.execute("SELECT id, name FROM income_sources").fetchall()
        inc_map = {r["name"].strip().lower(): r["id"] for r in inc_rows}

        for row in reader:
            row_type = row.get("type", "").strip().lower()
            date_str = row.get("date", "").strip()
            category_name = row.get("category", "").strip()
            income_source_name = row.get("income_source", "").strip()
            amount_str = row.get("amount", "").strip().replace(",", ".")
            currency = row.get("currency", "BYN").strip() or "BYN"
            comment = row.get("comment", "").strip()

            if not amount_str or not date_str:
                skipped += 1
                continue

            try:
                amount = round(float(amount_str), 2)
            except ValueError:
                skipped += 1
                continue

            if row_type == "expense":
                cat_key = category_name.lower()
                cat_id = cat_map.get(cat_key)
                if not cat_id:
                    # If category doesn't exist, create it in budget_categories
                    cur = conn.execute(
                        """
                        INSERT INTO budget_categories (name, planned_amount, currency, period, is_system, track_only, created_at)
                        VALUES (?, 0.0, ?, 'month', 0, 0, ?)
                        """,
                        (category_name or "Прочее", currency, now_iso()),
                    )
                    cat_id = cur.lastrowid
                    cat_map[cat_key] = cat_id

                # Check duplicate
                dup = conn.execute(
                    """
                    SELECT id FROM budget_entries
                    WHERE category_id = ? AND date = ? AND amount = ? AND comment = ?
                    """,
                    (cat_id, date_str, amount, comment),
                ).fetchone()

                if dup:
                    print(f"Skipping duplicate expense: {date_str} | {category_name} | {amount} BYN")
                    skipped += 1
                    continue

                conn.execute(
                    """
                    INSERT INTO budget_entries (category_id, amount, currency, date, comment, from_goal_id, created_at)
                    VALUES (?, ?, ?, ?, ?, NULL, ?)
                    """,
                    (cat_id, amount, currency, date_str, comment, now_iso()),
                )
                inserted_expenses += 1
                print(f"  + Расход: {date_str} | {category_name} | {amount:.2f} {currency} | {comment}")

            elif row_type == "income":
                src_id = None
                if income_source_name:
                    src_key = income_source_name.lower()
                    src_id = inc_map.get(src_key)
                    if not src_id:
                        cur = conn.execute(
                            """
                            INSERT INTO income_sources (name, type, planned_amount, currency, frequency, active, created_at)
                            VALUES (?, 'one_time', 0.0, ?, 'one_time', 1, ?)
                            """,
                            (income_source_name, currency, now_iso()),
                        )
                        src_id = cur.lastrowid
                        inc_map[src_key] = src_id

                # Check duplicate
                dup = conn.execute(
                    """
                    SELECT id FROM income_entries
                    WHERE (source_id = ? OR (source_id IS NULL AND ? IS NULL)) AND date = ? AND amount = ? AND comment = ?
                    """,
                    (src_id, src_id, date_str, amount, comment),
                ).fetchone()

                if dup:
                    print(f"Skipping duplicate income: {date_str} | {income_source_name} | {amount} BYN")
                    skipped += 1
                    continue

                conn.execute(
                    """
                    INSERT INTO income_entries (source_id, amount, currency, date, comment, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (src_id, amount, currency, date_str, comment, now_iso()),
                )
                inserted_incomes += 1
                print(f"  + Приход: {date_str} | {income_source_name or 'Разовый'} | {amount:.2f} {currency} | {comment}")

    print("\n--- Итог импорта ---")
    print(f"Внесено расходов: {inserted_expenses}")
    print(f"Внесено приходов: {inserted_incomes}")
    print(f"Пропущено дублей/ошибок: {skipped}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        path = sys.argv[1]
        with open(path, "r", encoding="utf-8") as f:
            data = f.read()
    else:
        data = sys.stdin.read()
    import_csv_data(data)
