# -*- coding: utf-8 -*-
"""Rate-Limiter: schuetzt den MQL5-Account vor Zuvielen-Requests.

- Mindestabstand zwischen zwei Requests (Default 2 s) + Zufalls-Jitter
- zusaetzliche Pause zwischen zwei Signalen (Default 5 s)
- Backoff bei HTTP 429/503 (Default 45 s, verdoppelt bis max. 3 Versuche)
Werte sind in der GUI (Admin-Bereich) konfigurierbar.
"""
from __future__ import annotations

import random
import time


class RateLimiter:
    def __init__(self, min_interval_s: float = 2.0, jitter_s: float = 1.0):
        self.min_interval_s = max(0.5, float(min_interval_s))
        self.jitter_s = max(0.0, float(jitter_s))
        self._last_request: float = 0.0

    def wait(self, extra_pause_s: float = 0.0) -> None:
        """Blockiert, bis der naechste Request erlaubt ist."""
        now = time.monotonic()
        gap = self.min_interval_s + random.uniform(0.0, self.jitter_s) + extra_pause_s
        elapsed = now - self._last_request
        if elapsed < gap:
            time.sleep(gap - elapsed)
        self._last_request = time.monotonic()


class Mql5ThrottleError(RuntimeError):
    """MQL5 drosselt uns (429/503) — nach Backoff immer noch blockiert."""


def backoff_after_throttle(attempt: int, base_s: float) -> float:
    """Wartezeit vor dem (attempt+1)-ten Versuch, attempt ab 0."""
    return base_s * (2 ** attempt)
