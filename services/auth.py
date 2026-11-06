import time
from collections import defaultdict
from werkzeug.security import check_password_hash, generate_password_hash

from config import APP_PIN

# Store hashed PIN so plain text isn't directly compared in memory
_PIN_HASH = generate_password_hash(str(APP_PIN))

# Rate limiting store: ip -> list of float timestamps of failed attempts
_FAILED_ATTEMPTS = defaultdict(list)
_LOCKOUT_DURATION = 300  # 5 minutes lockout
_MAX_ATTEMPTS = 5        # Max attempts before lockout


def check_rate_limit(ip: str) -> tuple[bool, int]:
    """Returns (is_allowed, seconds_remaining_if_blocked)."""
    now = time.time()
    # Filter attempts within the lockout window
    recent = [t for t in _FAILED_ATTEMPTS[ip] if now - t < _LOCKOUT_DURATION]
    _FAILED_ATTEMPTS[ip] = recent
    if len(recent) >= _MAX_ATTEMPTS:
        remaining = int(_LOCKOUT_DURATION - (now - recent[0]))
        return False, max(1, remaining)
    return True, 0


def record_failed_attempt(ip: str):
    _FAILED_ATTEMPTS[ip].append(time.time())


def clear_failed_attempts(ip: str):
    _FAILED_ATTEMPTS.pop(ip, None)


def verify_pin(pin: str, ip: str) -> tuple[bool, str | None]:
    """
    Verifies 4-digit PIN against hash with rate-limiting.
    Returns (is_valid, error_message).
    """
    allowed, remaining = check_rate_limit(ip)
    if not allowed:
        minutes = (remaining + 59) // 60
        return False, f"Слишком много неверных попыток. Попробуйте через {minutes} мин."

    if not pin or not pin.isdigit() or len(pin) != 4:
        record_failed_attempt(ip)
        return False, "Пин-код должен состоять из 4 цифр."

    if check_password_hash(_PIN_HASH, pin):
        clear_failed_attempts(ip)
        return True, None

    record_failed_attempt(ip)
    recent = [t for t in _FAILED_ATTEMPTS[ip] if time.time() - t < _LOCKOUT_DURATION]
    attempts_left = _MAX_ATTEMPTS - len(recent)
    if attempts_left > 0:
        return False, f"Неверный пин-код. Осталось попыток: {attempts_left}"
    return False, "Лимит попыток исчерпан. Доступ заблокирован на 5 минут."
