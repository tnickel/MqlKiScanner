# -*- coding: utf-8 -*-
"""Stufe 0 „Clients aktualisieren" — Daten der REST-Clients vor dem Scan
auf den neuesten Stand bringen (Konzept doc/23, Nutzer-Auftrag 07.10.2026).

Ablauf je aktiver Datenquelle (parallel):
  1. Bereitschaft: /health pollen (Client evtl. gerade von startall gestartet)
  2. POST /update  → Client startet seine Lade-Kaskade im Hintergrund
  3. GET /update/status pollen → Live-Fortschritt (phase/done/total/message)
  4. login_required → definiert warten (Nutzer kann im Client-Fenster tippen)
  5. done → Ergebnis übernehmen; error/timeout/offline → ehrlich melden

Das Modul fasst NUR einfache Dicts an (kein st.*) — es läuft im GUI-Worker-
Thread UND im autonomen scan_launcher. Bewertung findet hier nicht statt;
Stufe 0 beschafft nur Daten. Protokolliert wird je Quelle in die DB-Tabelle
`client_updates` (append-only, wie ampel_verlauf).
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import config, db, downloader_client, quellen

# Statuswerte je Quelle (stabil für UI/DB/Tests)
WARTET = "wartet"
BEREIT = "bereit"                    # health ok, POST folgt
LAEUFT = "laeuft"                    # Job running
LOGIN = "login"                      # Client wartet auf Login-Eingabe
FERTIG = "fertig"                    # Job done
FEHLER = "fehler"                    # Job error (rot)
TIMEOUT = "timeout"                  # Gesamt-/Login-Timeout überschritten
OFFLINE = "offline"                  # nie erreichbar
NICHT_UNTERSTUETZT = "nicht_unterstuetzt"  # 405: Client-Build zu alt
ABGEBROCHEN = "abgebrochen"          # Stop-Button

# Anzeigefarbe je Status für GUI (🟢 fertig · 🔵 läuft · 🟡 hinweis · 🔴 fehler)
STATUS_FARBE = {
    FERTIG: "gruen", LAEUFT: "blau", BEREIT: "blau", WARTET: "grau",
    LOGIN: "gelb", TIMEOUT: "gelb", OFFLINE: "gelb",
    NICHT_UNTERSTUETZT: "gelb", FEHLER: "rot", ABGEBROCHEN: "gelb",
}

# Zustände, nach denen die Poll-Schleife endet
_TERMINAL = {FERTIG, FEHLER, TIMEOUT, OFFLINE, NICHT_UNTERSTUETZT, ABGEBROCHEN}


def _neuer_zustand(quelle: dict) -> dict:
    return {
        "quelle_id": int(quelle["id"]),
        "kuerzel": str(quelle.get("kuerzel") or ""),
        "name": quellen.anzeige_name(quelle),
        "base_url": str(quelle.get("base_url") or ""),
        "status": WARTET,
        "phase": "",
        "detail": "Noch nicht gestartet",
        "done": 0, "total": 0,
        "job_id": "",
        "dauer_s": 0.0,
        "datenstand": "",
        "signale_geliefert": None,
        "tradelisten_neu": None,
        "tradelisten_aktualisiert": None,
        "katalog_uebersprungen": False,
        "hinweise": [],
        "fehler": "",
        "geaendert": datetime.now().isoformat(timespec="seconds"),
    }


def _setze(z: dict, **felder) -> None:
    """Status ändern + Zeitstempel — der Live-Dialog zeigt `geaendert`."""
    z.update(felder)
    z["geaendert"] = datetime.now().isoformat(timespec="seconds")


def _ergebnis_uebernehmen(z: dict, ergebnis: dict) -> None:
    """ergebnis-Block aus /update/status (doc/23 §4.2) in den Zustand holen."""
    ergebnis = ergebnis if isinstance(ergebnis, dict) else {}
    z["signale_geliefert"] = ergebnis.get("signaleGeliefert")
    z["tradelisten_neu"] = ergebnis.get("tradelistenNeu")
    z["tradelisten_aktualisiert"] = ergebnis.get("tradelistenAktualisiert")
    z["katalog_uebersprungen"] = bool(ergebnis.get("katalogUebersprungen"))
    z["datenstand"] = str(ergebnis.get("datenstand") or "")
    hinweise = ergebnis.get("hinweise") or []
    z["hinweise"] = [str(h) for h in hinweise][:10] if isinstance(hinweise, list) else []


def _bereit_warten(client, z: dict, *, warten_s: float, poll_s: float,
                   gestopft) -> bool:
    """/health pollen, bis der Client hochgefahren ist (startall-Fall)."""
    ende = time.monotonic() + max(0.0, warten_s)
    while True:
        if gestopft():
            _setze(z, status=ABGEBROCHEN, detail="Abbruch per Stop-Button (Bereitschaft)")
            return False
        try:
            info = client.health()
            if str(info.get("status", "")).lower() == "ok":
                _setze(z, status=BEREIT, detail="Client erreichbar — Update anstoßen …")
                return True
            _setze(z, detail=f"Unerwarteter Health-Status: {info.get('status')!r}")
        except downloader_client.DownloaderError as exc:
            _setze(z, detail=f"Warte auf Client … ({exc})")
        if time.monotonic() >= ende:
            _setze(z, status=OFFLINE, fehler=str(z["detail"]),
                   detail="Nicht erreichbar — läuft der Client (startall)?")
            return False
        time.sleep(poll_s)


def _persistiere(z: dict) -> None:
    """Ergebnis der Quelle in die Chronik-Tabelle (append-only)."""
    try:
        db.store_client_update(
            quelle_id=z["quelle_id"], kuerzel=z["kuerzel"], base_url=z["base_url"],
            job_id=z["job_id"], status=z["status"], dauer_s=z["dauer_s"],
            signale_geliefert=z["signale_geliefert"],
            tradelisten_neu=z["tradelisten_neu"],
            tradelisten_aktualisiert=z["tradelisten_aktualisiert"],
            datenstand=z["datenstand"], fehler=z["fehler"], hinweise=z["hinweise"])
    except Exception:
        pass  # Chronik darf den Update-Ablauf nie blockieren


def _zahl_aus_settings(settings: dict, schluessel: str, default: float) -> float:
    """EINE Lesart der Stufe-0-Zeit-/Zahl-Einstellungen (Mittel-4-Lektion
    von min_calmar_jahr: `or` macht aus einer eingestellten 0 den Default —
    0 Minuten Login-Timeout wäre aber eine gültige Wahl)."""
    wert = (settings or {}).get(schluessel)
    if wert is None or isinstance(wert, bool):
        return default
    try:
        zahl = float(wert)
    except (TypeError, ValueError, OverflowError):
        return default
    if zahl != zahl or zahl in (float("inf"), float("-inf")):
        return default
    return zahl


def _update_eine_quelle(quelle: dict, *, settings: dict, log, on_fortschritt,
                        gestopft, bereit_warten_s: float, poll_s: float,
                        backoff_s: float, timeout_s: float | None = None,
                        login_timeout_s: float | None = None) -> dict:
    """Kompletter Stufe-0-Ablauf für EINE Quelle. Liefert den finalen Zustand."""
    z = _neuer_zustand(quelle)

    # Log-Takt (doc/23 §6.4 „dezenter Takt"): identische Nachrichten höchstens
    # alle 30 s, echte Änderungen (Phase/Fortschritt) sofort. Der Live-Dialog
    # bekommt JEDE Meldung (on_fortschritt) — nur die Datei wird geschont.
    letzter_log: list = ["", 0.0]

    def _melde(detail: str = "", **felder) -> None:
        if detail:
            felder["detail"] = detail
        if felder:
            _setze(z, **felder)
        if log:
            nachricht = str(felder.get("detail") or z["detail"])
            jetzt = time.monotonic()
            if nachricht != letzter_log[0] or jetzt - letzter_log[1] >= 30.0:
                log(f"{z['kuerzel']}: {nachricht}")
                letzter_log[0] = nachricht
                letzter_log[1] = jetzt
        if on_fortschritt:
            try:
                on_fortschritt(dict(z))
            except Exception:
                pass  # Anzeige darf den Ablauf nie bremsen

    start = time.monotonic()
    try:
        client = quellen.client_fuer_quelle(quelle, timeout=8.0)
    except downloader_client.DownloaderError as exc:
        _melde(f"Quelle nicht nutzbar: {exc}", status=FEHLER, fehler=str(exc))
        z["dauer_s"] = round(time.monotonic() - start, 1)
        _persistiere(z)
        return z
    _melde("Warte auf Client (Bereitschaft) …")
    if not _bereit_warten(client, z, warten_s=bereit_warten_s, poll_s=poll_s,
                          gestopft=gestopft):
        z["dauer_s"] = round(time.monotonic() - start, 1)
        _persistiere(z)
        return z
    _melde()

    timeout_s = (max(60.0, _zahl_aus_settings(
        settings, "update_timeout_min", 120.0) * 60.0)
        if timeout_s is None else max(1.0, float(timeout_s)))
    login_timeout_s = (max(0.0, _zahl_aus_settings(
        settings, "update_login_timeout_min", 10.0) * 60.0)
        if login_timeout_s is None else max(0.0, float(login_timeout_s)))
    login_seit: float | None = None
    versuche_409 = 0
    # Einzelne Status-Poll-Fehlversuche (Netz-Schluckser) dürfen einen laufenden
    # Client nicht sofort rot machen — erst 3 in Folge (doc/23-Review 07.10.).
    status_fehler = 0

    while z["status"] not in _TERMINAL:
        if gestopft():
            _melde("Abbruch per Stop-Button", status=ABGEBROCHEN)
            break
        if z["status"] == BEREIT:
            try:
                antwort = client.update_starten(
                    target=int(_zahl_aus_settings(
                        settings, "update_ziel_signale", 200.0)),
                    tradelisten=True,
                    katalog_max_alter_h=int(_zahl_aus_settings(
                        settings, "update_katalog_max_alter_h", 72.0)),
                )
                z["job_id"] = str(antwort.get("jobId") or "")
                schon_laufend = bool(antwort.get("bereitsLaufend"))
                _melde("Update-Job läuft"
                       + (" (lief bereits — übernehme)" if schon_laufend else ""),
                       status=LAEUFT, phase="gestartet")
            except downloader_client.DownloaderBusy:
                versuche_409 += 1
                if versuche_409 >= 3:
                    _melde("Client bleibt beschäftigt (3× 409) — übersprungen",
                           status=TIMEOUT, fehler="Client dreimal beschäftigt (HTTP 409)")
                    break
                _melde(f"Client beschäftigt — erneuter Versuch in {backoff_s:.0f} s (409)")
                time.sleep(backoff_s)
            except downloader_client.DownloaderUpdateNotSupported as exc:
                _melde(str(exc), status=NICHT_UNTERSTUETZT, fehler=str(exc))
                break
            except downloader_client.DownloaderError as exc:
                _melde(f"Update-Anstoß fehlgeschlagen: {exc}", status=FEHLER,
                       fehler=str(exc))
                break
            continue
        # Status pollen
        try:
            info = client.update_status()
            status_fehler = 0
        except downloader_client.DownloaderError as exc:
            status_fehler += 1
            if status_fehler >= 3:
                grund = f"Statusabfrage 3× fehlgeschlagen: {exc}"
                _melde(grund, status=FEHLER, fehler=grund)
                break
            _melde(f"Statusabfrage fehlgeschlagen ({status_fehler}/3) — "
                   f"versuche weiter: {exc}")
            time.sleep(poll_s)
            continue
        state = str(info.get("state") or "").lower()
        phase = str(info.get("phase") or "")
        done = int(info.get("done") or 0)
        total = int(info.get("total") or 0)
        nachricht = str(info.get("message") or "")
        if info.get("ergebnis"):
            _ergebnis_uebernehmen(z, info.get("ergebnis"))
        if state == "done":
            _ergebnis_uebernehmen(z, info.get("ergebnis"))
            stand = z["datenstand"] or "?"
            katalog = (" (Katalog übersprungen — 3-Tage-Regel)"
                       if z["katalog_uebersprungen"] else "")
            _melde(f"Fertig — Datenstand {stand}{katalog}", status=FERTIG,
                   phase=phase, done=max(done, total), total=total)
            break
        if state == "error":
            fehler = str(info.get("error") or nachricht or "Client meldete Fehler")
            _melde(f"Fehler beim Update: {fehler}", status=FEHLER, fehler=fehler)
            break
        if state == "login_required":
            if login_seit is None:
                login_seit = time.monotonic()
                _melde(f"Client wartet auf Login-Eingabe ({nachricht or 'Login nötig'}) — "
                       f"Timeout {login_timeout_s / 60:.0f} min",
                       status=LOGIN, phase=phase)
            elif time.monotonic() - login_seit > login_timeout_s:
                _melde(f"Login-Timeout ({login_timeout_s / 60:.0f} min) — weiter mit "
                       "vorhandenem Datenstand", status=TIMEOUT,
                       fehler="Login wurde innerhalb des Timeouts nicht abgeschlossen")
                break
        else:
            login_seit = None
            _setze(z, status=LAEUFT, phase=phase, done=done, total=total)
            _melde(nachricht or f"Phase {phase or '…'}"
                   + (f" — {done}/{total}" if total else ""))
        if time.monotonic() - start > timeout_s:
            _melde(f"Gesamt-Timeout ({timeout_s / 60:.0f} min) — weiter mit "
                   "vorhandenem Datenstand", status=TIMEOUT,
                   fehler="Client-Update lief länger als das Gesamt-Timeout")
            break
        time.sleep(poll_s)

    z["dauer_s"] = round(time.monotonic() - start, 1)
    _setze(z)
    if on_fortschritt:
        try:
            on_fortschritt(dict(z))
        except Exception:
            pass
    _persistiere(z)
    return z


def starte_alle_updates(settings: dict, *, log=None, on_fortschritt=None,
                        gestopft=None, bereit_warten_s: float = 60.0,
                        poll_s: float = 5.0, backoff_s: float = 30.0,
                        timeout_s: float | None = None,
                        login_timeout_s: float | None = None) -> dict[str, dict]:
    """Stufe 0 für ALLE aktiven Quellen, parallel. Rückgabe kuerzel → Zustand.

    gestopft: Callable[[], bool] (Stop-Button). on_fortschritt: Callback mit
    Kopie des Zustands je Quelle (Live-Dialog). log: Zeilen-Funktion. Die
    Zeitparameter sind für Tests verkürzt; produktiv gelten die Defaults
    (None = aus den Settings: 120 min Gesamt, 10 min Login).
    """
    settings = settings or {}
    quellen._ensure()
    aktiv = db.list_quellen(nur_aktiv=True)
    zustaende = {str(q["kuerzel"]): _neuer_zustand(q) for q in aktiv}
    if not aktiv:
        if log:
            log("Keine aktive Datenquelle konfiguriert — Stufe 0 ohne Arbeit.")
        return zustaende
    if log:
        log(f"Stufe 0: Update bei {len(aktiv)} Client(s) anstoßen "
            f"(Ziel ≥{settings.get('update_ziel_signale', 200)} Signale, "
            f"Katalog-Frische {settings.get('update_katalog_max_alter_h', 72)} h) …")
    stop_flag = gestopft or (lambda: False)

    def _arbeit(quelle: dict) -> tuple[str, dict]:
        try:
            z = _update_eine_quelle(
                quelle, settings=settings, log=log, on_fortschritt=on_fortschritt,
                gestopft=stop_flag, bereit_warten_s=bereit_warten_s,
                poll_s=poll_s, backoff_s=backoff_s, timeout_s=timeout_s,
                login_timeout_s=login_timeout_s)
        except Exception as exc:  # eine Quelle darf nie die anderen mitreißen
            z = zustaende[str(quelle["kuerzel"])]
            _setze(z, status=FEHLER, fehler=f"{type(exc).__name__}: {exc}",
                   detail=f"Interner Fehler: {exc}")
            _persistiere(z)
        return str(quelle["kuerzel"]), z

    with ThreadPoolExecutor(max_workers=max(1, len(aktiv))) as pool:
        for kuerzel, z in pool.map(_arbeit, aktiv):
            zustaende[kuerzel] = z
    if log:
        log("Stufe-0-Bilanz: " + aggregat_text(zustaende))
    return zustaende


def aggregat_text(zustaende: dict[str, dict]) -> str:
    """Kurzbilanz für Log/Lauf-Zusammenfassung: „4 fertig · 1 mit Hinweis …"."""
    if not zustaende:
        return "keine Datenquellen aktiv"
    fertig = sum(1 for z in zustaende.values() if z["status"] == FERTIG)
    probleme = sum(1 for z in zustaende.values() if z["status"] == FEHLER)
    hinweise = len(zustaende) - fertig - probleme
    teile = [f"{fertig} fertig"]
    if hinweise:
        teile.append(f"{hinweise} mit Hinweis/übersprungen")
    if probleme:
        teile.append(f"{probleme} Fehler")
    return f"{len(zustaende)} Client(s): " + " · ".join(teile)


def alle_kritisch(zustaende: dict[str, dict]) -> bool:
    """True wenn JEDE Quelle endgültig 🔴 ist (offline zählt mit: kein Client
    hätte geliefert) — dann wäre der Scan reine Alt-Daten-Verarbeitung
    (doc/23 §6.2: Abbruch mit klarer Meldung statt Stillstand-Daten)."""
    werte = list(zustaende.values())
    return bool(werte) and all(z["status"] in (FEHLER, OFFLINE) for z in werte)


def mit_hinweisen(zustaende: dict[str, dict]) -> bool:
    """True wenn mindestens eine Quelle nicht sauber fertig wurde (🟡-Läufe)."""
    return any(z["status"] != FERTIG for z in zustaende.values())
