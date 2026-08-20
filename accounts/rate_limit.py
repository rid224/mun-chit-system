from django.conf import settings
from django.core.cache import cache


def _cache_key(identifier: str) -> str:
    return f"login_attempts:{identifier}"


def get_attempt_count(identifier: str) -> int:
    return cache.get(_cache_key(identifier), 0)


def register_failed_attempt(identifier: str) -> int:
    key = _cache_key(identifier)
    count = cache.get(key, 0) + 1
    cache.set(key, count, timeout=settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS)
    return count


def clear_attempts(identifier: str) -> None:
    cache.delete(_cache_key(identifier))


def is_rate_limited(identifier: str) -> bool:
    return get_attempt_count(identifier) >= settings.LOGIN_RATE_LIMIT_ATTEMPTS


def rate_limit_identifier(request, email: str) -> str:
    """Combine IP + email so one bad actor can't lock out a shared IP's other users,
    while still throttling repeated guesses against a single account."""
    ip = request.META.get("REMOTE_ADDR", "unknown")
    return f"{ip}:{email.lower().strip()}"
