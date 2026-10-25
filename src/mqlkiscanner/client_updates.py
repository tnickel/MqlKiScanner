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

import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import config, db, downloader_client, quellen

_LOG = logging.getLogger(__name__)
_FALLBACK_LOCK = threading.Lock()

# Statuswerte je Quelle (stabil für UI/DB/Tests)
WARTET = "wartet"
BEREIT = "bereit"                    # health ok, POST folgt
LAEUFT = "laeuft"                    # Job running
LOGIN = "login"                      # Client wartet auf Login-Eingabe
FERTIG = "fertig"                    # Job done
TEILWEISE = "teilweise"              # Job beendet, Datenaktualisierung teilweise fehlgeschlagen
FEHLER = "fehler"                    # Job error (rot)
TIMEOUT = "timeout"                  # Gesamt-/Login-Timeout überschritten
OFFLINE = "offline"                  # nie erreichbar
NICHT_UNTERSTUETZT = "nicht_unterstuetzt"  # 405: Client-Build zu alt
ABGEBROCHEN = "abgebrochen"          # Stop-Button

# Anzeigefarbe je Status für GUI (🟢 fertig · 🔵 läuft · 🟡 hinweis · 🔴 fehler)
STATUS_FARBE = {
    FERTIG: "gruen", LAEUFT: "blau", BEREIT: "blau", WARTET: "grau",
    TEILWEISE: "gelb",
    LOGIN: "gelb", TIMEOUT: "gelb", OFFLINE: "gelb",
    NICHT_UNTERSTUETZT: "gelb", FEHLER: "rot", ABGEBROCHEN: "gelb",
}

# Zustände, nach denen die Poll-Schleife endet
_TERMINAL = {FERTIG, TEILWEISE, FEHLER, TIMEOUT, OFFLINE, NICHT_UNTERSTUETZT, ABGEBROCHEN}


def _neuer_zustand(quelle: dict, modus: str = "scan") -> dict:
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
        "tradelisten_fehler": 0,
        "tradelisten_abgebrochen": False,
        "katalog_uebersprungen": False,
        "hinweise": [],
        "fehler": "",
        "modus": str(modus),
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
    try:
        z["tradelisten_fehler"] = max(0, int(ergebnis.get("tradelistenFehler") or 0))
    except (TypeError, ValueError, OverflowError):
        z["tradelisten_fehler"] = 0
    z["tradelisten_abgebrochen"] = ergebnis.get("tradelistenAbgebrochen") is True
    z["katalog_uebersprungen"] = bool(ergebnis.get("katalogUebersprungen"))
    z["datenstand"] = str(ergebnis.get("datenstand") or "")
    hinweise = ergebnis.get("hinweise") or []
    z["hinweise"] = [str(h) for h in hinweise][:10] if isinstance(hinweise, list) else []


def _abonnenten_katalog(ergebnis: dict) -> dict | None:
    """Validate optional coverage receipts; skipped slots are not provider IDs."""
    fields = ("subscriberCatalogComplete", "subscriberCatalogReachedEnd",
              "subscriberCatalogScanned", "subscriberCatalogSkippedPositions",
              "subscriberCatalogMonths", "subscriberCatalogSort")
    if not any(key in ergebnis for key in fields):
        return None  # A missing receipt is explicitly unconfirmed below.
    complete, end, scanned, skipped, months, sort = (ergebnis.get(key) for key in fields)
    if (type(complete) is not bool or end is not True
            or type(scanned) is not int or scanned < 0
            or not isinstance(skipped, list)
            or any(type(n) is not int or n <= 0 for n in skipped)
            or len(set(skipped)) != len(skipped)
            or type(months) is not int or months not in (1, 3, 6, 12)
            or not isinstance(sort, str) or not sort.strip()
            or complete != (not skipped)):
        raise ValueError("Ungültiger Beleg zur Abdeckung des Abonnentenkatalogs")
    return dict(complete=complete, reached_end=True, scanned_providers=scanned,
                skipped_positions=sorted(skipped), months=months, sort=sort)


def _mql_abonnenten_auswahl(ergebnis: dict, target: int) -> dict:
    """Both MT prefixes need target/zero proof; visible paging is no exhaustion."""
    if (ergebnis.get("subscriberSelectionVerified") is not True
            or type(ergebnis.get("subscriberSelectionTarget")) is not int
            or ergebnis["subscriberSelectionTarget"] != target):
        raise ValueError("MQL-Client bestätigt keinen aktuellen Abonnenten-Auswahlbeleg; Client aktualisieren")
    platforms = ergebnis.get("subscriberSelectionPlatforms")
    if not isinstance(platforms, dict) or set(platforms) != {"mql4", "mql5"}:
        raise ValueError("MQL-Auswahlbeleg muss MT4 und MT5 enthalten")
    receipt = {}
    for version, proof in platforms.items():
        if not isinstance(proof, dict):
            raise ValueError("Ungültiger MQL-Abonnenten-Auswahlbeleg")
        count, reached, zero = (proof.get(k) for k in ("collected", "targetReached", "zeroBoundaryReached"))
        if (type(count) is not int or not 0 <= count <= target
                or type(reached) is not bool or reached != (count == target)
                or type(zero) is not bool or not (reached or zero)):
            raise ValueError("MQL-Abonnentenliste ohne belegtes Ziel oder Nullgrenze")
        receipt[version] = dict(collected=count, targetReached=reached, zeroBoundaryReached=zero)
    if ergebnis.get("signaleGeliefert") != min(target, sum(p["collected"] for p in receipt.values())):
        raise ValueError("MQL-Auswahlgröße widerspricht den beiden Plattformbelegen")
    return dict(verified=True, target=target, platforms=receipt)


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
                z["abonnenten_refresh_unterstuetzt"] = info.get("abonnentenRefresh") is True
                z["mql_abonnenten_auswahlbeleg_unterstuetzt"] = info.get("subscriberSelectionProof") is True
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
    """Append evidence to the existing DB, with a local ignored fallback on failure."""
    hinweise = list(z["hinweise"])
    # Modus-Kennzeichnung (doc/24): „abonnenten"-Läufe (nur Katalog/Abos,
    # keine Tradelisten) sind in der Chronik sofort erkennbar. Der normale
    # Scan-Modus bleibt unverändert („scan" wird nicht mitgeschrieben).
    if z.get("modus") and z["modus"] != "scan":
        hinweise.insert(0, f"Modus: {z['modus']}")
    if z.get("detail"):
        hinweise.append(str(z["detail"]))
    if z.get("abonnenten_auswahl"):
        hinweise.append("MQL-Auswahlbeleg: " + json.dumps(z["abonnenten_auswahl"], ensure_ascii=False, sort_keys=True))
    payload = dict(
        quelle_id=z["quelle_id"], kuerzel=z["kuerzel"], base_url=z["base_url"],
        job_id=z["job_id"], status=z["status"], dauer_s=z["dauer_s"],
        signale_geliefert=z["signale_geliefert"], tradelisten_neu=z["tradelisten_neu"],
        tradelisten_aktualisiert=z["tradelisten_aktualisiert"],
        datenstand=z["datenstand"], fehler=z["fehler"], hinweise=hinweise)
    try:
        db.store_client_update(**payload)
    except Exception as exc:
        # Runtime .log files are already excluded by .gitignore. Store only the
        # same public job metadata as the DB, never request headers or tokens.
        fallback = config.DATA_DIR / "client_updates_fallback.log"
        try:
            event = dict(payload, ts=datetime.now().isoformat(timespec="seconds"),
                         chronik_fehler=f"{type(exc).__name__}: {exc}")
            with _FALLBACK_LOCK:
                fallback.parent.mkdir(parents=True, exist_ok=True)
                with fallback.open("a", encoding="utf-8") as output:
                    output.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
                    output.flush()
                    os.fsync(output.fileno())
            message = f"Stufe-0-Chronik nicht in DB gespeichert; lokaler Beleg: {fallback}"
        except Exception as fallback_error:
            message = ("Stufe-0-Chronik weder in DB noch im lokalen Fallback gespeichert: "
                       f"{type(fallback_error).__name__}")
        try:
            _LOG.error(message)
        except Exception:
            pass  # Logging cannot replace the actual source outcome or abort.


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
                        login_timeout_s: float | None = None,
                        tradelisten: bool = True,
                        katalog_max_alter_h: float | None = None,
                        modus: str = "scan") -> dict:
    """Kompletter Stufe-0-Ablauf für EINE Quelle. Liefert den finalen Zustand.

    tradelisten=False + katalog_max_alter_h=0 ist der Abonnenten-Refresh
    (doc/24 §4 Stufe B): nur Katalog/Abonnenten neu messen, keine Trades.
    """
    z = _neuer_zustand(quelle, modus=modus)
    start = time.monotonic()
    unterbrechung = None
    try:
        # A process killed without Python cleanup still leaves an unfinished
        # start trace. Never turn that trace into an invented completed run.
        _persistiere(dict(z, detail="Stufe 0 begonnen; Abschluss steht aus"))
        return _update_eine_quelle_ablauf(
            quelle, z=z, settings=settings, log=log, on_fortschritt=on_fortschritt,
            gestopft=gestopft, bereit_warten_s=bereit_warten_s, poll_s=poll_s,
            backoff_s=backoff_s, timeout_s=timeout_s, login_timeout_s=login_timeout_s,
            tradelisten=tradelisten, katalog_max_alter_h=katalog_max_alter_h)
    except Exception as exc:
        _setze(z, status=FEHLER, fehler=f"{type(exc).__name__}: {exc}",
               detail=f"Interner Fehler: {type(exc).__name__}: {exc}")
        return z
    except BaseException as exc:
        unterbrechung = exc
        _setze(z, status=ABGEBROCHEN, fehler=f"{type(exc).__name__}: {exc}",
               detail=f"Stufe 0 unterbrochen ({type(exc).__name__})"
                      + ("; Ende des Client-Jobs unbekannt" if z["job_id"] else ""))
        raise
    finally:
        z["dauer_s"] = round(time.monotonic() - start, 1)
        _setze(z)
        try:
            _persistiere(z)
            if on_fortschritt:
                try:
                    on_fortschritt(dict(z))
                except Exception:
                    pass
        except BaseException:
            if unterbrechung is None:
                raise  # Preserve an existing KeyboardInterrupt/SystemExit cause.


def _update_eine_quelle_ablauf(quelle: dict, *, z: dict, settings: dict, log, on_fortschritt,
                             gestopft, bereit_warten_s: float, poll_s: float,
                             backoff_s: float, timeout_s: float | None,
                             login_timeout_s: float | None,
                             tradelisten: bool = True,
                             katalog_max_alter_h: float | None = None) -> dict:
    """Source protocol; final evidence and callbacks belong to the outer wrapper."""

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
        return z
    _melde("Warte auf Client (Bereitschaft) …")
    if not _bereit_warten(client, z, warten_s=bereit_warten_s, poll_s=poll_s,
                          gestopft=gestopft):
        z["dauer_s"] = round(time.monotonic() - start, 1)
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
            _melde("Abbruch per Stop-Button"
                   + (" — Überwachung beendet; Client-Job kann weiterlaufen"
                      if z["job_id"] else ""), status=ABGEBROCHEN)
            break
        if z["status"] == BEREIT:
            nur_abonnenten = z.get("modus") == "abonnenten"
            if nur_abonnenten and not z.get("abonnenten_refresh_unterstuetzt"):
                grund = "Client unterstützt den Top-200-Zählerrefresh noch nicht; aktualisierten Client starten."
                _melde(grund, status=NICHT_UNTERSTUETZT, fehler=grund)
                break
            if (nur_abonnenten and db.kanonische_quelle(z["kuerzel"]) in {"mql4", "mql5"}
                    and not z.get("mql_abonnenten_auswahlbeleg_unterstuetzt")):
                grund = "MQL-Client unterstützt keinen belegten Top-200-Abschluss; aktualisierten Client starten."
                _melde(grund, status=NICHT_UNTERSTUETZT, fehler=grund)
                break
            try:
                # katalog_max_alter_h: None = Setting-Wert (Default 72 h,
                # 3-Tage-Regel); 0 erzwingt die Katalog-Neumessung — nötig
                # für den Abonnenten-Refresh, sonst überspringe der Client
                # die Katalog-Phase und misst nichts neu (doc/24 §4).
                alter_h = (float(katalog_max_alter_h)
                           if katalog_max_alter_h is not None
                           else _zahl_aus_settings(
                               settings, "update_katalog_max_alter_h", 72.0))
                extra = {"nur_abonnenten": True} if nur_abonnenten else {}
                antwort = client.update_starten(
                    target=int(_zahl_aus_settings(
                        settings, "update_ziel_signale", 200.0)),
                    tradelisten=bool(tradelisten),
                    katalog_max_alter_h=int(max(0.0, alter_h)),
                    **extra,
                )
                z["job_id"] = str(antwort.get("jobId") or "")
                if nur_abonnenten and not z["job_id"]:
                    grund = "Client bestätigt den neuen Zählerauftrag ohne Job-ID; kein Frischenachweis."
                    _melde(grund, status=FEHLER, fehler=grund)
                    break
                schon_laufend = bool(antwort.get("bereitsLaufend"))
                if nur_abonnenten and schon_laufend:
                    grund = "Client arbeitet bereits; vorhandener Job ist kein Nachweis einer neuen Zählermessung."
                    _melde(grund, status=FEHLER, fehler=grund)
                    break
                _melde("Update-Job läuft"
                       + (" (lief bereits — übernehme)" if schon_laufend else ""),
                       status=LAEUFT, phase="gestartet")
                _persistiere(dict(z, detail="Client-Job gestartet oder übernommen; Abschluss steht aus"))
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
        status_job_id = str(info.get("jobId") or "")
        if z.get("modus") == "abonnenten" and not status_job_id:
            grund = "Status des Zählerrefreshs enthält keine Job-ID; kein Frischenachweis."
            _melde(grund, status=FEHLER, fehler=grund)
            break
        if z['job_id'] and status_job_id and status_job_id != z['job_id']:
            grund = (f"Status gehört zu anderem Update-Job ({status_job_id}); "
                     f"erwartet {z['job_id']} — kein Erfolgsnachweis.")
            _melde(grund, status=FEHLER, fehler=grund)
            break
        phase = str(info.get("phase") or "")
        try:
            done = int(info.get("done") or 0)
            total = int(info.get("total") or 0)
        except (TypeError, ValueError):
            done, total = 0, 0
        nachricht = str(info.get("message") or "")
        if info.get("ergebnis"):
            _ergebnis_uebernehmen(z, info.get("ergebnis"))
        if state == "done":
            if z.get("modus") == "abonnenten" and (
                    not isinstance(info.get("ergebnis"), dict)
                    or info["ergebnis"].get("nurAbonnenten") is not True):
                grund = "Client meldet keinen Abschluss des angeforderten Zählerrefreshs."
                _melde(grund, status=FEHLER, fehler=grund)
                break
            if z.get("modus") == "abonnenten":
                geliefert = info["ergebnis"].get("signaleGeliefert")
                if (isinstance(geliefert, bool) or not isinstance(geliefert, int)
                        or not 0 <= geliefert <= 200
                        or info["ergebnis"].get("katalogUebersprungen") is True):
                    grund = "Client bestätigt keinen frischen Katalog mit höchstens 200 Anbietern."
                    _melde(grund, status=FEHLER, fehler=grund)
                    break
                try:
                    if db.kanonische_quelle(z["kuerzel"]) in {"mql4", "mql5"}:
                        target = min(200, max(1, int(_zahl_aus_settings(settings, "update_ziel_signale", 200.0))))
                        z["abonnenten_auswahl"] = _mql_abonnenten_auswahl(info["ergebnis"], target)
                    coverage = _abonnenten_katalog(info["ergebnis"])
                    if coverage is not None:
                        if coverage["scanned_providers"] < geliefert:
                            raise ValueError("Auswahl ist größer als der geprüfte Abonnentenkatalog")
                        z["abonnenten_katalog"] = coverage
                    z["abonnenten_auswahl_unbestaetigt"] = (
                        coverage is None and not z.get("abonnenten_auswahl", {}).get("verified"))
                except ValueError as exc:
                    _melde(str(exc), status=FEHLER, fehler=str(exc))
                    break
            _ergebnis_uebernehmen(z, info.get("ergebnis"))
            stand = z["datenstand"] or "?"
            katalog = (" (Katalog übersprungen — 3-Tage-Regel)"
                       if z["katalog_uebersprungen"] else "")
            catalog_gaps = z.get("abonnenten_katalog", {}).get("complete") is False
            selection_unknown = z.get("abonnenten_auswahl_unbestaetigt") is True
            teilweise = z["tradelisten_fehler"] > 0 or z["tradelisten_abgebrochen"] or catalog_gaps or selection_unknown
            detail = (f"Teilweise aktualisiert — {z['tradelisten_fehler']} Tradelistenfehler; "
                      f"Jobende {stand}{katalog}" if teilweise
                      else f"Fertig — Datenstand {stand}{katalog}")
            if catalog_gaps:
                slots = z["abonnenten_katalog"]["skipped_positions"]
                warning = (f"{len(slots)} API-Position(en) ausgelassen; Auswahl aus lesbaren "
                           "Anbietern, globale Top 200 unbestätigt.")
                z["hinweise"] = list(dict.fromkeys([*z["hinweise"], warning]))
                detail = f"Mit Kataloglücken aktualisiert — {warning} Datenstand {stand}"
            elif selection_unknown:
                warning = ("Abonnentenauswahl/Abdeckung unbestätigt: Client liefert keinen "
                           "Auswahl- oder Katalogbeleg; globale Top 200 nicht bestätigt.")
                z["hinweise"] = list(dict.fromkeys([*z["hinweise"], warning]))
                detail = f"Zähler aktualisiert mit unbestätigter Auswahl — {warning} Datenstand {stand}"
            _melde(detail, status=TEILWEISE if teilweise else FERTIG,
                   phase=phase, done=done if teilweise else max(done, total), total=total)
            break
        if state == "cancelled":
            grund = str(info.get("error") or nachricht or "Client hat den Auftrag abgebrochen")
            _melde(f"Client-Auftrag abgebrochen: {grund}", status=ABGEBROCHEN, fehler=grund,
                   phase=phase, done=done, total=total)
            break
        if state == "error":
            fehler = str(info.get("error") or nachricht or "Client meldete Fehler")
            _melde(f"Fehler beim Update: {fehler}", status=FEHLER, fehler=fehler)
            break
        if state == "login_required":
            if login_seit is None:
                login_seit = time.monotonic()
                # Nutzer-Hinweis 25.10.: Der Text muss sagen, WO getippt wird —
                # nämlich im Fenster des Clients, nicht im Scanner/Browser.
                # Die Fettmarkierung setzt die UI-Schicht (Status login).
                _melde(f"Login erforderlich — bitte jetzt im Fenster von "
                       f"{z['kuerzel']} einloggen ({nachricht or 'Login nötig'}) "
                       f"— Timeout {login_timeout_s / 60:.0f} min",
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

    return z


def starte_alle_updates(settings: dict, *, log=None, on_fortschritt=None,
                        gestopft=None, bereit_warten_s: float = 60.0,
                        poll_s: float = 5.0, backoff_s: float = 30.0,
                        timeout_s: float | None = None,
                        login_timeout_s: float | None = None,
                        tradelisten: bool = True,
                        katalog_max_alter_h: float | None = None,
                        quellen_filter=None, modus: str = "scan") -> dict[str, dict]:
    """Stufe 0 für aktive Quellen, parallel. Rückgabe kuerzel → Zustand.

    gestopft: Callable[[], bool] (Stop-Button). on_fortschritt: Callback mit
    Kopie des Zustands je Quelle (Live-Dialog). log: Zeilen-Funktion. Die
    Zeitparameter sind für Tests verkürzt; produktiv gelten die Defaults
    (None = aus den Settings: 120 min Gesamt, 10 min Login).

    Abonnenten-Variante (doc/24 §4 Stufe B): tradelisten=False lädt NUR
    Katalog/Abonnenten (keine Tradelisten), katalog_max_alter_h=0 erzwingt
    die Neumessung trotz 3-Tage-Regel, quellen_filter begrenzt auf die
    gewählten Kürzel, modus markiert die Chronik (z. B. "abonnenten").
    """
    settings = settings or {}
    quellen._ensure()
    aktiv = db.list_quellen(nur_aktiv=True)
    if quellen_filter:
        erlaubt = {db.kanonische_quelle(k) for k in quellen_filter}
        aktiv = [q for q in aktiv if db.kanonische_quelle(q["kuerzel"]) in erlaubt]
    zustaende = {str(q["kuerzel"]): _neuer_zustand(q, modus=modus) for q in aktiv}
    if not aktiv:
        if log:
            log("Keine (gewählte) aktive Datenquelle konfiguriert — "
                "Stufe 0 ohne Arbeit.")
        return zustaende
    if log:
        if not tradelisten:
            log(f"Stufe 0 (nur Katalog/Abonnenten): Update bei {len(aktiv)} "
                f"gewählter Client(s) anstoßen — Katalog-Frische erzwingen, "
                "keine Tradelisten.")
        else:
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
                login_timeout_s=login_timeout_s, tradelisten=tradelisten,
                katalog_max_alter_h=katalog_max_alter_h, modus=modus)
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
