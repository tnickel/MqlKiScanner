# -*- coding: utf-8 -*-
"""MQL5-Session: Login-Flow, Cookie-Verwaltung, gedrosselte Requests.

Login (doc/02 Abschnitt 2):
1. GET /en/auth_login  -> Formular (Login- + Passwortfeld + Hidden-Felder)
2. POST der Credentials -> Redirect = eingeloggt; Session-Cookie merken
3. Export-Aufruf mit Cookie
4. Erfolgs-Check: CSV-Antwort beginnt mit "Time;". Beginnt sie mit
   "<!DOCTYPE" und enthaelt "Log in" -> Session weg, neu einloggen.

Credentials kommen ausschliesslich aus secrets_store (Umgebung/.env/
secrets.local.json) — nie als Parameter durch die GUI-UI-Geschichte reichen.
"""
from __future__ import annotations

import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .. import secrets_store
from ..config import MQL5_BASE
from .ratelimit import Mql5ThrottleError, RateLimiter, backoff_after_throttle

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


class Mql5Session:
    def __init__(self, settings: dict | None = None):
        self.settings = settings or {}
        self.http = requests.Session()
        self.http.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en"})
        self.logged_in = False
        self.limiter = RateLimiter(
            min_interval_s=self.settings.get("rate_min_interval_s", 2.0),
        )

    # -------------------------------------------------------------- Login
    @property
    def has_credentials(self) -> bool:
        return bool(secrets_store.get_secret("mql5_user")
                    and secrets_store.get_secret("mql5_pass"))

    def login(self, extra_pause_s: float = 0.0) -> bool:
        """MQL5-Login. True = eingeloggt (oder schon eingeloggt)."""
        if not self.has_credentials:
            raise RuntimeError(
                "Keine MQL5-Credentials gesetzt (Admin-Bereich oder MQL5_USER/MQL5_PASS).")
        user = secrets_store.get_secret("mql5_user")
        password = secrets_store.get_secret("mql5_pass")

        self.limiter.wait(extra_pause_s)
        r = self.http.get(urljoin(MQL5_BASE, "/en/auth_login"), timeout=30)
        soup = BeautifulSoup(r.text, "html.parser")
        form = soup.find("form", action=lambda a: a and "auth_login" in a) or soup.find("form")
        if form is None:
            # Bereits eingeloggt? Dann zeigt die Seite kein Login-Formular.
            if self.is_logged_in():
                self.logged_in = True
                return True
            raise RuntimeError("Login-Formular nicht gefunden.")

        payload: dict[str, str] = {}
        for inp in form.find_all("input"):
            name = inp.get("name")
            if not name:
                continue
            if inp.get("type", "text").lower() == "password":
                payload[name] = password
            elif inp.get("type", "text").lower() in ("text", "email", "tel"):
                payload[name] = user
            elif inp.get("type", "text").lower() in ("hidden", "checkbox", "radio"):
                payload[name] = inp.get("value", "")
        action = urljoin(MQL5_BASE, form.get("action") or "/en/auth_login")

        self.limiter.wait()
        r = self.http.post(action, data=payload, timeout=30)
        self.logged_in = self.is_logged_in()
        return self.logged_in

    def is_logged_in(self) -> bool:
        """Eingeloggt-Check ueber die eigene Signalseite (Login-Link weg)."""
        try:
            self.limiter.wait()
            r = self.http.get(urljoin(MQL5_BASE, "/en"), timeout=30)
            return 'href="/en/logout' in r.text or "Log out" in r.text
        except requests.RequestException:
            return False

    # ------------------------------------------------------------ Request
    def get(self, path_or_url: str, extra_pause_s: float = 0.0,
            max_throttle_retries: int = 3) -> requests.Response:
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
            r.raise_for_status()
            return r
        raise Mql5ThrottleError(
            f"MQL5 drosselt weiter (HTTP {r.status_code}) nach "
            f"{max_throttle_retries} Backoff-Versuchen: {url}")

    def ensure_session_for_export(self) -> None:
        """Vor Exporten: Session pruefen/erneuern (doc/02 Fehlerquelle)."""
        if self.logged_in and self.is_logged_in():
            return
        self.login()

    def export_positions_csv(self, signal_id: int, extra_pause_s: float = 0.0) -> str:
        """Trade-Export je Signal (doc/02: Antwort muss mit 'Time;' beginnen)."""
        self.ensure_session_for_export()
        r = self.get(f"/en/signals/{signal_id}/export/positions",
                     extra_pause_s=extra_pause_s)
        text = r.text
        if text.lstrip().startswith("Time;"):
            return text
        if text.lstrip().startswith("<!DOCTYPE"):
            # Session zwischendurch weg -> einmal neu einloggen und wiederholen
            self.login()
            r = self.get(f"/en/signals/{signal_id}/export/positions",
                         extra_pause_s=extra_pause_s)
            if r.text.lstrip().startswith("Time;"):
                return r.text
        raise RuntimeError(
            f"Export fuer Signal {signal_id} lieferte kein CSV (Login-HTML?). "
            "Credentials pruefen bzw. MQL5-Status kontrollieren.")
