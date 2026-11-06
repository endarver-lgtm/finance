import os
import time
from collections import defaultdict
from werkzeug.security import check_password_hash, generate_password_hash

import config

# Progressive rate limiting storage:
# ip -> list of float timestamps of failed attempts
_FAILED_ATTEMPTS: dict[str, list[float]] = defaultdict(list)
_GLOBAL_FAILED_ATTEMPTS: list[float] = []

_BASE_LOCKOUT = 900          # 15 minutes lockout after 5 attempts
_EXTENDED_LOCKOUT = 3600     # 60 minutes lockout after 10 attempts
_MAX_ATTEMPTS = 5            # Max attempts before initial lockout
_GLOBAL_THRESHOLD = 50       # Global threshold within 10 min window to prevent distributed attacks
_GLOBAL_WINDOW = 600         # 10 minutes


def _get_target_hash() -> str:
    """Generate salted PBKDF2:SHA256 hash with 600,000 iterations for the configured secret."""
    secret = str(os.environ.get("APP_PASSWORD") or os.environ.get("APP_PIN") or config.APP_PASSWORD)
    # Using 600,000 iterations of PBKDF2-HMAC-SHA256 (NIST recommendation for high-security credential hashing)
    return generate_password_hash(secret, method="pbkdf2:sha256:600000")


# Cache the hash in memory
_CACHED_HASH = _get_target_hash()


def reload_credentials():
    """Call when environment or configuration changes."""
    global _CACHED_HASH
    _CACHED_HASH = _get_target_hash()


def check_rate_limit(ip: str) -> tuple[bool, int, str]:
    """
    Returns (is_allowed, seconds_remaining, reason).
    Enforces per-IP progressive lockout and global throttling against botnets.
    """
    now = time.time()

    # 1. Check global throttle
    global _GLOBAL_FAILED_ATTEMPTS
    _GLOBAL_FAILED_ATTEMPTS = [t for t in _GLOBAL_FAILED_ATTEMPTS if now - t < _GLOBAL_WINDOW]
    if len(_GLOBAL_FAILED_ATTEMPTS) >= _GLOBAL_THRESHOLD:
        return False, 300, "Превышен глобальный лимит попыток авторизации. Защитная блокировка."

    # 2. Check per-IP attempts
    attempts = [t for t in _FAILED_ATTEMPTS[ip] if now - t < _EXTENDED_LOCKOUT]
    _FAILED_ATTEMPTS[ip] = attempts

    total_recent = len(attempts)
    if total_recent >= 10:
        elapsed = now - attempts[0]
        remaining = int(_EXTENDED_LOCKOUT - elapsed)
        if remaining > 0:
            return False, remaining, f"Слишком много неудачных попыток. IP заблокирован на {(remaining + 59)//60} мин."
    elif total_recent >= _MAX_ATTEMPTS:
        elapsed = now - attempts[-_MAX_ATTEMPTS]
        remaining = int(_BASE_LOCKOUT - elapsed)
        if remaining > 0:
            return False, remaining, f"Слишком много попыток. IP временно заблокирован на {(remaining + 59)//60} мин."

    return True, 0, ""


def record_failed_attempt(ip: str):
    now = time.time()
    _FAILED_ATTEMPTS[ip].append(now)
    _GLOBAL_FAILED_ATTEMPTS.append(now)


def clear_failed_attempts(ip: str):
    _FAILED_ATTEMPTS.pop(ip, None)


def verify_credential(credential: str, ip: str) -> tuple[bool, str | None]:
    """
    Verifies password or PIN against PBKDF2-SHA256 (600,000 iterations).
    Supports passphrases, alphanumeric passwords, and multi-digit PINs (>= 4 chars).
    Returns (is_valid, error_message).
    """
    allowed, remaining, reason = check_rate_limit(ip)
    if not allowed:
        return False, reason

    if not credential or len(credential.strip()) < 4:
        record_failed_attempt(ip)
        return False, "Пароль или PIN должен содержать не менее 4 символов."

    # Verify with constant-time hash comparison
    if check_password_hash(_CACHED_HASH, credential.strip()):
        clear_failed_attempts(ip)
        return True, None

    # Failed attempt
    record_failed_attempt(ip)
    now = time.time()
    recent = [t for t in _FAILED_ATTEMPTS[ip] if now - t < _BASE_LOCKOUT]
    attempts_left = max(0, _MAX_ATTEMPTS - len(recent))

    if attempts_left > 0:
        return False, f"Неверный пароль или PIN. Осталось попыток до блокировки: {attempts_left}"
    return False, "Превышен лимит попыток. Доступ заблокирован на 15 минут."


# Backward-compatible alias
verify_pin = verify_credential
