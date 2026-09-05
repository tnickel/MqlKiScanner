# -*- coding: utf-8 -*-
"""MQL5-Session: Cookie-HTTP-Client, gedrosselte Requests, Export.

Anmeldung: MQL5 verlangt ein per JavaScript gesetztes Cookie. Reine
HTTP-Formular-Logins scheitern deshalb systematisch. Login laeuft ueber
browser_session.ensure_mql5_cookies (Selenium); diese Klasse nutzt die
geernteten Cookies fuer schnelle HTTP-Abrufe inkl. Rate-Limit.
"""
from __future__ import annotations

import time
from urllib.parse import urljoin

import requests

from .. import secrets_store
from ..config import MQL5_BASE
from .ratelimit import Mql5HardStopError, Mql5ThrottleError, RateLimiter, backoff_after_throttle

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def export_kinds_for_platform(platform: str | None) -> tuple[str, ...]:
    """MT4: history (Orderbuch); MT5: positions. Unbekannt: beide versuchen."""
    p = (platform or "").strip().upper()
    if p == "MT4":
        return ("history", "positions")
    if p == "MT5":
        return ("positions", "history")
    return ("positions", "history")


class Mql5Session:
    def __init__(self, settings: dict | None = None):
        self.settings = settings or {}
        self.http = requests.Session()
        self.http.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en"})
        self.logged_in = False
        self.limiter = RateLimiter(
            min_interval_s=self.settings.get("rate_min_interval_s", 2.0),
        )

    @property
    def has_credentials(self) -> bool:
        return bool(secrets_store.get_secret("mql5_user")
                    and secrets_store.get_secret("mql5_pass"))

    def is_logged_in(self) -> bool:
        """Eingeloggt-Check: MQL5 zeigt den Abmelde-Link als
        /en/auth_logout (Text 'Logout'); alte Varianten mitgeprüft."""
        try:
            self.limiter.wait()
            r = self.http.get(urljoin(MQL5_BASE, "/en"), timeout=30)
            return ("/en/auth_logout" in r.text
                    or 'href="/en/logout' in r.text
                    or ">Logout<" in r.text
                    or "Log out" in r.text)
        except requests.RequestException:
            return False

    def get(self, path_or_url: str, extra_pause_s: float = 0.0,
            max_throttle_retries: int = 3,
            allow_http_statuses: tuple[int, ...] = ()) -> requests.Response:
        """GET mit Rate-Limit und Backoff bei 429/503."""
        url = urljoin(MQL5_BASE + "/", path_or_url)
        for attempt in range(max_throttle_retries):
            self.limiter.wait(extra_pause_s)
            r = self.http.get(url, timeout=60)
            if r.status_code in (429, 503):
                wait_s = backoff_after_throttle(
                    attempt, float(self.settings.get("rate_backoff_429_s", 45.0)))
                time.sleep(wait_s)
                continue
            if r.status_code == 403:
                raise Mql5HardStopError(
                    f"MQL5 antwortet mit HTTP 403 (Sperre/Verbot) für {url}")
            if r.status_code in allow_http_statuses:
                return r
            r.raise_for_status()
            return r
        raise Mql5ThrottleError(
            f"MQL5 drosselt weiter (HTTP {r.status_code}) nach "
            f"{max_throttle_retries} Backoff-Versuchen: {url}")

    def ensure_session_for_export(self) -> None:
        """Vor Exporten: Session pruefen; bei Bedarf Browser-Login (nicht HTTP)."""
        if not self.has_credentials:
            raise RuntimeError(
                "Keine MQL5-Credentials gesetzt (Admin-Bereich oder "
                "MQL5_USER/MQL5_PASS) — Trade-Export nicht moeglich.")
        if self.logged_in and self.is_logged_in():
            return
        # Bewusst kein HTTP-Formular-Login: MQL5 verlangt JS-Cookies.
        from .browser_session import ensure_mql5_cookies
        if not ensure_mql5_cookies(self.settings, self):
            raise RuntimeError(
                "MQL5-Browser-Login fehlgeschlagen — Zugangsdaten unter "
                "Einstellungen prüfen und „MQL5-Login testen“.")
        self.logged_in = True

    def export_positions_csv(self, signal_id: int, extra_pause_s: float = 0.0,
                             platform: str | None = None) -> str:
        """Trade-Export je Signal (doc/02: Antwort muss mit 'Time;' beginnen).

        MT5: /export/positions — MT4: /export/history (positions → 404).
        BOM-tolerant und retry-tolerant. Bei Login-HTML: Browser-Session
        erneuern (ensure_session_for_export), dann erneut versuchen.
        """
        self.ensure_session_for_export()
        kinds = export_kinds_for_platform(platform)
        last_text = ""
        last_status = None
        tried: list[str] = []
        for kind in kinds:
            path = f"/en/signals/{signal_id}/export/{kind}"
            tried.append(kind)
            for attempt in range(3):
                r = self.get(path, extra_pause_s=extra_pause_s,
                             allow_http_statuses=(404,))
                last_status = r.status_code
                if r.status_code == 404:
                    break  # falscher Export-Typ → naechsten kind
                text = r.text.lstrip("\ufeff")
                if text.lstrip().startswith("Time;"):
                    return text
                last_text = text
                if text.lstrip().startswith("<!DOCTYPE") and "auth_login" in text:
                    self.logged_in = False
                    self.ensure_session_for_export()
                time.sleep(10 * (attempt + 1))
        raise RuntimeError(
            f"Export fuer Signal {signal_id} (Plattform={platform or '?'}, "
            f"versucht: {', '.join(tried)}) lieferte kein CSV "
            f"(letzter HTTP {last_status}, Anfang: {last_text[:80]!r}). "
            "Moegliche Ursache: temporaere Drosselung oder Session-Sperre; "
            "in ein paar Minuten erneut versuchen oder den Cache nutzen.")
