"""Optional HTTP admission for one research run; no requests or budgets here."""
from __future__ import annotations

import math
import threading
import time
from contextlib import contextmanager
from datetime import timezone
from email.utils import parsedate_to_datetime


class AdaptiveHttpGate:
    """Bound actual requests and share provider throttling across private clients.

    ``check_stop`` must raise the caller's cancellation exception. Slot waiting
    checks it at least every ``poll_s`` seconds; no budget ticket exists yet.
    Callbacks are notifications only and never run under the admission lock.
    """

    def __init__(self, max_limit=10, *, initial_limit=None, check_stop=None, log=None,
                 on_change=None, cooldown_s=15.0, max_cooldown_s=60.0,
                 recovery_successes=10, recovery_interval_s=60.0, poll_s=0.5,
                 monotonic=time.monotonic, wall_time=time.time, wait=None):
        initial_limit = max_limit if initial_limit is None else initial_limit
        if (type(max_limit) is not int or not 1 <= max_limit <= 10
                or type(initial_limit) is not int or not 1 <= initial_limit <= max_limit
                or type(recovery_successes) is not int or recovery_successes < 1):
            raise ValueError("Invalid research HTTP concurrency limits")
        for value in (cooldown_s, max_cooldown_s, recovery_interval_s, poll_s):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError("Research HTTP delays must be positive and finite")
        if max_cooldown_s < cooldown_s or poll_s > 0.5:
            raise ValueError("Invalid research HTTP cooldown or cancellation interval")
        self._max, self._limit = max_limit, initial_limit
        self._active = self._max_active = self._throttles = self._streak = self._successes = 0
        self._until = 0.0
        self._last_recovery = monotonic()
        self._cooldown, self._max_cooldown = cooldown_s, max_cooldown_s
        self._recovery_successes, self._recovery_interval, self._poll = recovery_successes, recovery_interval_s, poll_s
        self._clock, self._wall_time = monotonic, wall_time
        self._check = check_stop or (lambda: None)
        self._log, self._on_change = log, on_change
        self._condition = threading.Condition()
        self._notification_lock = threading.RLock()
        self._wait = wait or (lambda condition, delay: condition.wait(timeout=delay))

    def check_stop(self):
        self._check()

    def backoff(self, seconds):
        """Legacy retry delay outside a request slot, with cooperative stop."""
        until = self._clock()+seconds
        while True:
            self.check_stop()
            with self._condition:
                remaining = until-self._clock()
                if remaining <= 0:
                    return
                self._wait(self._condition, min(self._poll, remaining))

    def status(self):
        with self._condition:
            return dict(limit=self._limit, active=self._active, max_active=self._max_active,
                        throttles=self._throttles, requested_limit=self._max,
                        cooldown_remaining_s=max(0.0, self._until-self._clock()))

    def _notify(self, message=None):
        # Serialize notifications separately from admission. Read the snapshot
        # only after taking this lock so callbacks cannot publish older peaks
        # after newer ones while other request threads continue independently.
        with self._notification_lock:
            if self._on_change:
                try:
                    self._on_change(self.status())
                except Exception:
                    pass  # A display callback cannot lose a paid response or a slot.
            if message and self._log:
                try:
                    self._log(message)
                except Exception:
                    pass

    @contextmanager
    def slot(self):
        acquired = False
        try:
            while not acquired:
                self.check_stop()
                with self._condition:
                    remaining = self._until-self._clock()
                    if remaining <= 0 and self._active < self._limit:
                        self._active += 1
                        self._max_active = max(self._max_active, self._active)
                        acquired = True
                    else:
                        self._wait(self._condition, min(self._poll, remaining) if remaining > 0 else self._poll)
            self._notify()
            self.check_stop()
            yield
        finally:
            if acquired:
                with self._condition:
                    self._active -= 1
                    self._condition.notify_all()
                self._notify()

    def _retry_after(self, response):
        value = (getattr(response, "headers", None) or {}).get("Retry-After")
        if value is None:
            return 0.0
        try:
            delay = float(value)
        except (TypeError, ValueError):
            try:
                target = parsedate_to_datetime(str(value))
                if target.tzinfo is None:
                    target = target.replace(tzinfo=timezone.utc)
                delay = target.timestamp()-self._wall_time()
            except (TypeError, ValueError, OverflowError):
                return 0.0
        return max(0.0, delay) if math.isfinite(delay) else 0.0

    def observe(self, response):
        """Observe an already settled HTTP response; never retry it here."""
        status = getattr(response, "status_code", 0)
        try:
            body = response.json()
            error = body.get("error") if isinstance(body, dict) else None
            code = str(error.get("code") or "") if isinstance(error, dict) else ""
        except (ValueError, TypeError, AttributeError):
            code = ""
        limited = status == 429 or code == "1302"
        message = None
        changed = False
        with self._condition:
            current = self._clock()
            if limited:
                self._throttles += 1
                self._streak += 1
                self._successes = 0
                self._limit = max(1, self._limit//2)
                delay = max(min(self._max_cooldown, self._cooldown * 2**min(self._streak-1, 16)),
                            self._retry_after(response))
                self._until = max(self._until, current+delay)
                self._last_recovery = current
                message = f"KI-Anbieter drosselt: HTTP-Limit {self._limit}/{self._max}; gemeinsame Wartezeit {self._until-current:.1f} s."
                changed = True
            elif isinstance(status, int) and 200 <= status < 400:
                self._successes += 1
                if (self._limit < self._max and current >= self._until
                        and current-self._last_recovery >= self._recovery_interval
                        and self._successes >= self._recovery_successes):
                    self._limit += 1
                    self._successes = self._streak = 0
                    self._last_recovery = current
                    message = f"KI-Anbieter wieder stabil: HTTP-Limit vorsichtig auf {self._limit}/{self._max} erhöht."
                    changed = True
            if changed:
                self._condition.notify_all()
        if changed:
            self._notify(message)
