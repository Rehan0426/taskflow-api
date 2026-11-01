"""Login rate limiter with an abstract interface so Redis can replace the in-memory store.

Why this module exists:
Brute-force password stuffing targets `/auth/login`. By keying rate limits on `(ip_address, email)`,
an attacker cannot lock out legitimate users from other IPs while still blocking targeted guessing
from a single source. Defining `RateLimiterBackend` as a Protocol makes swapping in Redis a
15-line change when scaling to multiple Uvicorn workers.
"""

import math
import time
from collections import defaultdict
from threading import Lock
from typing import Protocol

from app.core.config import settings
from app.core.exceptions import RateLimitError
from app.core.logging import logger


class RateLimiterBackend(Protocol):
    """Interface for login failure rate limiters (In-Memory or Redis)."""

    def check_or_raise(self, key: str) -> None:
        """Raise RateLimitError if key has exceeded max failed attempts within the window."""
        ...

    def record_failure(self, key: str) -> None:
        """Record a failed attempt timestamp for key."""
        ...

    def reset(self, key: str) -> None:
        """Clear failures for key after a successful login."""
        ...


class InMemoryLoginRateLimiter:
    """Thread-safe sliding-window in-memory rate limiter for failed logins."""

    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def _prune(self, key: str, now: float) -> list[float]:
        cutoff = now - self.window_seconds
        valid = [ts for ts in self._attempts.get(key, []) if ts > cutoff]
        if valid:
            self._attempts[key] = valid
        else:
            self._attempts.pop(key, None)
        return valid

    def check_or_raise(self, key: str) -> None:
        """Check current sliding window and raise 429 with Retry-After if limit reached."""
        now = time.monotonic()
        with self._lock:
            valid = self._prune(key, now)
            if len(valid) >= self.max_attempts:
                oldest = valid[0]
                retry_after = max(1, math.ceil((oldest + self.window_seconds) - now))
                logger.warning("Rate limit exceeded for key=%s retry_after=%ds", key, retry_after)
                raise RateLimitError(retry_after=retry_after)

    def record_failure(self, key: str) -> None:
        """Append a failed login timestamp inside the sliding window."""
        now = time.monotonic()
        with self._lock:
            self._prune(key, now)
            self._attempts[key].append(now)

    def reset(self, key: str) -> None:
        """Clear recorded failures on successful login."""
        with self._lock:
            self._attempts.pop(key, None)

    def clear_all(self) -> None:
        """Reset all keys (used by test fixtures)."""
        with self._lock:
            self._attempts.clear()


login_rate_limiter = InMemoryLoginRateLimiter(
    max_attempts=settings.LOGIN_RATE_LIMIT_MAX_ATTEMPTS,
    window_seconds=settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
)
