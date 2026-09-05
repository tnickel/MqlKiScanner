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


class Mql5HardStopError(RuntimeError):
    """Systemische MQL5-Sperre/Drosselung — Pipeline soll Fail-Fast abbrechen."""

    def __init__(self, message: str, result=None):
        super().__init__(message)
        self.result = result


def is_hard_mql5_failure(exc: BaseException | str) -> bool:
    """Erkennt Fehler, die eher Account-/IP-Sperre als Einzel-Signal-Pech sind."""
    text = str(exc)
    needles = (
        "Mql5ThrottleError",
        "Mql5HardStopError",
        "drosselt weiter",
        "HTTP 403",
        "HTTP 429",
        "HTTP 503",
        "auth_login",
        "Login-HTML",
        "lieferte kein CSV",
        "Browser-Login fehlgeschlagen",
        "Incorrect login",
        "MQL5-Login fehlgeschlagen",
        "Login über Browser nicht bestätigt",
    )
    return any(n.casefold() in text.casefold() for n in needles)


def backoff_after_throttle(attempt: int, base_s: float) -> float:
    """Wartezeit vor dem (attempt+1)-ten Versuch, attempt ab 0."""
    return base_s * (2 ** attempt)
