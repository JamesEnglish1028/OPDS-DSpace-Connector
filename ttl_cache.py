import threading
import time
from typing import Any


class TTLCache:
    """A small in-memory TTL cache for JSON-like payloads."""

    def __init__(self, ttl_seconds: float = 60.0):
        self.ttl_seconds = ttl_seconds
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str):
        now = time.time()
        with self._lock:
            record = self._data.get(key)
            if record is None:
                return None

            expires_at, value = record
            if expires_at <= now:
                del self._data[key]
                return None

            return value

    def set(self, key: str, value: Any):
        expires_at = time.time() + self.ttl_seconds
        with self._lock:
            self._data[key] = (expires_at, value)

    def clear(self):
        with self._lock:
            self._data.clear()
