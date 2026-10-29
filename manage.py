"""Управление проектом: python manage.py [reset|update-rates]"""

import sys

from db import reset_db


def main():
    if len(sys.argv) < 2:
        print("Команды:")
        print("  reset        — очистить БД и создать заново")
        print("  update-rates — обновить курсы валют (USD, EUR) по API НБРБ")
        sys.exit(1)
    cmd = sys.argv[1].lower()
    if cmd == "reset":
        reset_db()
        print("База очищена. Таблицы в SQLite пересозданы с настройками BYN.")
        return
    if cmd in ("update-rates", "rates", "sync-rates"):
        from services.nbrb import sync_rates_from_nbrb

        try:
            res = sync_rates_from_nbrb()
            print(f"Курсы успешно обновлены по данным НБРБ (на {res['nbrb_date']}):")
            print(f"  1 USD = {res['usd_rate']} BYN")
            print(f"  1 EUR = {res['eur_rate']} BYN")
        except Exception as e:
            print(f"Ошибка при обновлении курсов: {e}")
            sys.exit(1)
        return
    print(f"Неизвестная команда: {cmd}")
    sys.exit(1)


if __name__ == "__main__":
    main()
