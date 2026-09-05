# -*- coding: utf-8 -*-
"""Browser-basierter MQL5-Login und Trade-Export (Selenium-Chrome).

Warum: MQL5 schuetzt den Login mit einem JavaScript berechneten Cookie
(MediaToken/_media_uuid) und verweigert reine HTTP-Logins pauschal mit
"Incorrect login" — unabhaengig von den Zugangsdaten. Bewaehrte Loesung
aus dem MqlDownloader-Projekt: echter Chrome (Selenium) meldet an, die
Cookies werden geerntet und der requests-Session uebergeben. Danach
laufen Kennzahlen-Seiten und die meisten Trade-Exporte wieder ueber
schnelle HTTP-Abrufe (Rate-Limiter greift weiter).

Der CSV-Export selbst folgt dem MqlDownloader-Ablauf: Signal-Seite
oeffnen, "Trading History"-Tab klicken, "History"-Export-Link klicken
— Chrome laedt die Datei in ein Staging-Verzeichnis, aus dem sie nach
data/trades/{id}_positions.csv verschoben wird.

Der Chrome nutzt ein PERSISTENTES Profil (data/chrome_profile) — die
Anmeldung ueberlebt App-Neustarts. Cookie-Datei: data/mql5_cookies.json
(gitignored, enthaelt Session-Berechtigungen!).
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from .. import secrets_store
from ..config import DATA_DIR
from .session import Mql5Session

COOKIE_FILE = DATA_DIR / "mql5_cookies.json"
PROFILE_DIR = DATA_DIR / "chrome_profile"
TRADES_DIR = DATA_DIR / "trades"
DOWNLOAD_DIR = TRADES_DIR / "_download"


def load_saved_cookies() -> dict[str, str] | None:
    if not COOKIE_FILE.exists():
        return None
    try:
        data = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
        return data.get("cookies") or None
    except (json.JSONDecodeError, OSError):
        return None


def save_cookies(cookies: dict[str, str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    COOKIE_FILE.write_text(
        json.dumps({"cookies": cookies, "gespeichert": time.strftime("%Y-%m-%d %H:%M")},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        import os
        os.chmod(COOKIE_FILE, 0o600)
    except OSError:
        pass


def _apply_cookies(session: Mql5Session, cookies: dict[str, str]) -> None:
    for name, value in cookies.items():
        session.http.cookies.set(name, value, domain=".mql5.com")


def _logged_in(session: Mql5Session) -> bool:
    return session.is_logged_in()


def ensure_mql5_cookies(settings: dict, session: Mql5Session,
                        force_browser_login: bool = False,
                        log=None) -> bool:
    """Stellt sicher, dass `session` eingeloggt ist.

    Reihenfolge: gespeicherte Cookies pruefen -> falls ungueltig und
    Credentials vorhanden: Selenium-Chrome-Login (echter Browser, JS
    laeuft) -> Cookies ernten und speichern. True = session ist
    eingeloggt. `log` ist ein optionaler Callback fuer Statuszeilen.
    """
    def _info(msg: str) -> None:
        if log:
            log(msg)

    if not force_browser_login:
        saved = load_saved_cookies()
        if saved:
            _apply_cookies(session, saved)
            if _logged_in(session):
                _info("MQL5-Session aus gespeicherten Cookies gültig.")
                return True
            _info("Gespeicherte MQL5-Cookies abgelaufen — Browser-Anmeldung nötig.")
    return _login_via_browser(settings, session, log)


# --------------------------------------------------------------- Selenium
def _start_driver(download_dir: Path | None = None):
    """Chrome mit persistentem Profil starten; optional mit Download-Dir."""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
    except ImportError:
        raise RuntimeError(
            "selenium ist nicht installiert (pip install selenium) — "
            "Browser-Login nicht möglich.")

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    options = Options()
    options.add_argument(f"--user-data-dir={PROFILE_DIR}")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    if download_dir is not None:
        download_dir.mkdir(parents=True, exist_ok=True)
        options.add_experimental_option("prefs", {
            "download.default_directory": str(download_dir),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "profile.default_content_settings.popups": 0,
        })
    return webdriver.Chrome(service=Service(), options=options)


def _driver_login(driver, user: str, password: str) -> None:
    """Formular-Login im geoeffneten Chrome (Muster: MqlDownloader)."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

    wait = WebDriverWait(driver, 45)
    driver.get("https://www.mql5.com/en/auth_login")

    # Entweder erscheint das Login-Formular, oder das persistente Profil
    # leitet als eingeloggt gleich weiter — beides abwarten, nicht raten.
    try:
        wait.until(lambda d: d.find_elements(By.ID, "Login")
                   or "/auth_login" not in d.current_url)
    except Exception:
        pass
    time.sleep(1)

    if driver.find_elements(By.ID, "Login"):
        user_field = driver.find_element(By.ID, "Login")
        user_field.clear()
        user_field.send_keys(user)
        pw_field = driver.find_element(By.ID, "Password")
        pw_field.clear()
        pw_field.send_keys(password)
        # Bewaehrt aus MqlDownloader: gelber Submit-Button per JS klicken
        try:
            btn = driver.find_element(By.ID, "loginSubmit")
        except Exception:
            btn = driver.find_element(
                By.CSS_SELECTOR, "input.button.button_yellow.qa-submit")
        driver.execute_script("arguments[0].click();", btn)
        # Nach dem Login landet man auf /en (Redirect weg vom Formular)
        try:
            wait.until(lambda d: "/auth_login" not in d.current_url
                       and not d.find_elements(By.ID, "Login"))
        except Exception:
            pass
        time.sleep(2)


def _login_via_browser(settings: dict, session: Mql5Session, log=None) -> bool:
    """Oeffnet Chrome, meldet mit den hinterlegten Zugängen an, erntet Cookies."""
    user = secrets_store.get_secret("mql5_user")
    password = secrets_store.get_secret("mql5_pass")
    if not (user and password):
        raise RuntimeError(
            "Keine MQL5-Credentials gesetzt (Admin-Bereich oder "
            "MQL5_USER/MQL5_PASS) — Browser-Login nicht möglich.")

    def _info(msg: str) -> None:
        if log:
            log(msg)

    _info("Öffne Chrome für die MQL5-Anmeldung (Fenster erscheint kurz) …")
    driver = _start_driver()
    try:
        _driver_login(driver, user, password)
        driver.get("https://www.mql5.com/en")
        time.sleep(1.5)
        if driver.find_elements("id", "Login") or "/auth_login" in driver.current_url:
            raise RuntimeError(
                "MQL5 hat die Anmeldung im Browser nicht akzeptiert "
                "(weiterhin ausgeloggt) — Zugangsdaten im Admin-Bereich prüfen.")

        cookies = {c["name"]: c["value"] for c in driver.get_cookies()
                   if c.get("domain", "").endswith("mql5.com")}
        save_cookies(cookies)
        _apply_cookies(session, cookies)
        ok = _logged_in(session)
        _info("MQL5-Anmeldung im Browser erfolgreich — Cookies übernommen."
              if ok else "Browser meldet Login, aber Cookie-Check unklar — "
              "erneut versuchen.")
        return ok
    finally:
        try:
            driver.quit()
        except Exception:
            pass


# ------------------------------------------------- CSV-Export im Browser
def export_positions_via_browser(signal_id: int, log=None) -> str:
    """Laedt die Trade-Historie als CSV — MqlDownloader-Muster.

    Ablauf: Chrome mit persistentem Profil oeffnen (eingeloggter Zustand
    haelt), Signal-Seite oeffnen, "Trading History"-Tab klicken,
    "History"-Export-Link klicken, Download im Staging-Verzeichnis
    abwarten und nach data/trades/{id}_positions.csv verschieben.
    Rueckgabe: Pfad der CSV.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

    def _info(msg: str) -> None:
        if log:
            log(msg)

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    # Staging leeren, damit die neue Datei eindeutig ist
    for old in DOWNLOAD_DIR.iterdir():
        try:
            old.unlink()
        except OSError:
            pass

    user = secrets_store.get_secret("mql5_user")
    password = secrets_store.get_secret("mql5_pass")

    driver = _start_driver(download_dir=DOWNLOAD_DIR)
    try:
        wait = WebDriverWait(driver, 45)
        driver.get(f"https://www.mql5.com/en/signals/{signal_id}")
        time.sleep(1.5)
        if driver.find_elements(By.ID, "Login"):
            if not (user and password):
                raise RuntimeError("Kein MQL5-Login — Export über Browser nicht möglich.")
            _info("  Chrome ist ausgeloggt — Anmeldung läuft …")
            _driver_login(driver, user, password)
            driver.get(f"https://www.mql5.com/en/signals/{signal_id}")
            time.sleep(1.5)

        # "Trading History"-Tab (Sprachvarianten wie im MqlDownloader)
        tab = wait.until(lambda d: next((el for el in d.find_elements(
            By.XPATH, "//*[text()='Trading history' or text()='Handelshistorie' "
            "or text()='Trading History']") if el.is_displayed()), None))
        driver.execute_script("arguments[0].click();", tab)
        time.sleep(1.5)

        # "History"-Export-Link (letzter der Liste, wie im MqlDownloader)
        export_links = driver.find_elements(
            By.XPATH, "//*[text()='History' or text()='Historie']")
        if not export_links:
            raise RuntimeError(
                f"Kein History-Export-Link auf der Signal-Seite {signal_id} gefunden.")
        driver.execute_script("arguments[0].click();", export_links[-1])
        _info("  CSV-Download gestartet (Chrome) …")

        # Auf die Datei warten (Chrome schreibt erst .crdownload)
        csv_file = None
        deadline = time.time() + 30
        while time.time() < deadline:
            candidates = [f for f in DOWNLOAD_DIR.iterdir()
                          if f.suffix == ".csv" and not f.name.endswith(".crdownload")]
            if candidates:
                csv_file = candidates[0]
                break
            time.sleep(0.5)
        if not csv_file:
            raise RuntimeError(
                f"Chrome hat innerhalb von 30 s keine CSV für Signal "
                f"{signal_id} geliefert.")

        head = csv_file.read_text(encoding="utf-8-sig", errors="replace")[:64].lstrip()
        if not head.startswith("Time;"):
            try:
                csv_file.unlink(missing_ok=True)
            except OSError:
                pass
            raise RuntimeError(
                f"Chrome-Download für Signal {signal_id} ist kein Positions-CSV "
                f"(Anfang: {head[:80]!r}). Datei verworfen — kein Cache-Eintrag.")

        target = TRADES_DIR / f"{signal_id}_positions.csv"
        shutil.move(str(csv_file), target)
        _info(f"  ✓ CSV über Chrome geladen: {target.name}")
        return str(target)
    finally:
        try:
            driver.quit()
        except Exception:
            pass
