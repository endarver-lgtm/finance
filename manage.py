"""Управление проектом: python manage.py reset"""

import sys

from db import reset_db


def main():
    if len(sys.argv) < 2:
        print("Команды: reset — очистить БД и создать заново")
        sys.exit(1)
    cmd = sys.argv[1].lower()
    if cmd == "reset":
        reset_db()
        print("База очищена. Таблицы в Postgres пересозданы с настройками BYN.")
        return
    print(f"Неизвестная команда: {cmd}")
    sys.exit(1)


if __name__ == "__main__":
    main()
