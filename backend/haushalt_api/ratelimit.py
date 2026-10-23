"""Brute-force protection for the login: after LOGIN_MAX_FAILURES failed
attempts for one username and client address, further attempts are refused
for LOGIN_BLOCK_SECONDS. In memory - enough for one API process."""

import threading
import time

from . import config


class FailureLimiter:
    def __init__(self, max_failures: int, block_seconds: int):
        self.max_failures = max_failures
        self.block_seconds = block_seconds
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> list[float]:
        recent = [t for t in self._failures.get(key, []) if now - t < self.block_seconds]
        if recent:
            self._failures[key] = recent
        else:
            self._failures.pop(key, None)
        return recent

    def blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._recent(key, time.monotonic())) >= self.max_failures

    def failure(self, key: str) -> None:
        with self._lock:
            now = time.monotonic()
            self._failures[key] = self._recent(key, now) + [now]

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


login_limiter = FailureLimiter(config.LOGIN_MAX_FAILURES, config.LOGIN_BLOCK_SECONDS)
