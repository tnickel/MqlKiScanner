# -*- coding: utf-8 -*-
"""Abonnentenstatistik — zentrale Zuwachs-Übersicht über alle Quellen (doc/24).

Nutzer-Wunsch 20.10.2026: „wo laufen die meisten Nutzer hin?" — die Seite
zeigt je Quelle (Tab) und gesamt (Tab „Alle") die aktuellen Abonnentenzahlen
plus Zuwächse (seit letzter Messung / 7 Tage / 30 Tage) als Kandidaten-
Heuristik VOR dem Workflow. Sie bewertet NICHT: Ampel und Urteil bleiben
beim Workflow; hier wird nur beobachtet und gemessen.

Datenfluss (doc/24 §3): Jeder Sync liest je aktiver Quelle den Vollkatalog
(``minSubscribers=0``, validierte Pagination über ingest.hole_katalog) UND
die komplette Abonnenten-Historie je Provider aus der Client-DB
(``GET /providers/{id}/{v}/history``, Millisekunden) in die Scanner-Tabelle
``subscriber_history``. Nur echte native Historien liefern Messzeitpunkte;
Katalogabrufe erzeugen keine eigenen Jetztpunkte und damit keine Tagesfrische.
Ein expliziter Refresh erneuert die nativen Zählerhistorien vor dem Spiegeln. Die Δ-Werte
berechnet der Scanner einheitlich selbst (die Client-Felder weekChange/
monthChange werden bewusst NICHT gemischt — deren Semantik je Client
differiert). Tradelisten werden nie geladen.

Refresh-Modell (doc/24 §4, Nutzer-Entscheidung 20.10.2026):
  Stufe A „nur neu lesen"  — sync() über alle aktiven Quellen (~Sekunden
  bis Minuten; Zahlen so frisch wie der letzte Client-Lauf).
  Stufe B „frisch messen"  — POST /api/v1/update {"tradelisten": false,
  "katalogMaxAlterH": 0} je gewählter Quelle über die Stufe-0-Maschinerie
  (client_updates.starte_alle_updates mit tradelisten=False — die Clients
  laden NUR Katalog/Abonnenten neu, keine Tradelisten), danach automatisch
  Stufe A. katalogMaxAlterH=0 erzwingt die Neumessung; ohne es würde die
  3-Tage-Regel der Clients die Katalog-Phase überspringen.
"""
from __future__ import annotations

import copy
import io
import threading
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Callable
from uuid import uuid4

from . import config, db, downloader_client, ingest, katalog, quellen
from .downloader_sync import _bilanz as _bilanz_reihe

# Fenster der Tabellen-Sparkline („Verlauf 30 T"), relativ zum NEUESTEN
# Messpunkt — dieselbe Semantik wie das Sparkline-Fenster des MqlDownloaders
# (SubscriberStatisticsDialog.SparklineData.fromLast30Days).
_SPARKLINE_FENSTER_TAGE = 30


def sparkline_png(werte, *, trend: int, breite: int = 88,
                  hoehe: int = 22) -> bytes | None:
    """Mini-Verlaufskurve als transparentes PNG für die Tabellenspalte.

    trend > 0 zeichnet grün, < 0 rot, 0 grau (Netto des Fensters). Weniger
    als 2 Punkte ergeben KEINE Kurve (None) — keine erfundene Entwicklung.
    Rein rechnerisch, bewertet nichts; Aufrufer cacht das Ergebnis.
    """
    zahlen = [int(w) for w in werte if w is not None]
    if len(zahlen) < 2:
        return None
    from PIL import Image, ImageDraw  # lazy: Modul bleibt ohne GUI-Stack nutzbar
    richtung = (trend > 0) - (trend < 0)
    farbe = {1: (76, 175, 80), -1: (239, 83, 80)}.get(richtung, (158, 158, 158))
    bild = Image.new("RGBA", (breite, hoehe), (0, 0, 0, 0))
    zeichnen = ImageDraw.Draw(bild)
    lo, hi = min(zahlen), max(zahlen)
    spanne = (hi - lo) or 1
    xs = [round(i * (breite - 5) / (len(zahlen) - 1)) + 2
          for i in range(len(zahlen))]
    ys = [hoehe - 3 - round((w - lo) / spanne * (hoehe - 6)) for w in zahlen]
    zeichnen.line(list(zip(xs, ys)), fill=farbe + (255,), width=2)
    zeichnen.ellipse([xs[-1] - 2, ys[-1] - 2, xs[-1] + 2, ys[-1] + 2],
                     fill=farbe + (255,))
    puffer = io.BytesIO()
    bild.save(puffer, "PNG", optimize=True)
    return puffer.getvalue()

# Katalog-Abruf mit großzügigerem Timeout als der Standard-Client: der
# MqlDownloader braucht für 372 Zeilen mit Wochen-Dateialter-Scan kalt
# bis ~10 s (gemessen 20.10.2026).
_KATALOG_TIMEOUT_S = 30.0


def _parse_ts(wert) -> datetime | None:
    try:
        return datetime.fromisoformat(str(wert))
    except (TypeError, ValueError):
        return None


def _vergleichspunkt(reihe: list[tuple[datetime, int]], tage: int) -> int | None:
    """Abonnentenstand des Messpunkts vor ~tagen Tagen (±3 Tage Toleranz).

    Dieselbe Auswahlregel wie downloader_sync._bilanz (nächstliegender
    Punkt am Zieltermin) — hierfür braucht die Prozentspalte die BASIS,
    nicht nur die Differenz. Ein Konsistenz-Test hält beide synchron.
    """
    ziel = datetime.now() - timedelta(days=tage)
    kandidaten = [(ts, wert) for ts, wert in reihe
                  if wert is not None
                  and abs((ts - ziel).total_seconds()) <= 3 * 86400]
    if not kandidaten:
        return None
    return min(kandidaten, key=lambda x: abs((x[0] - ziel).total_seconds()))[1]


# ── Sync: Katalog + belegte native Historie ──────────────────────────────
def sync_quelle(quelle: dict, *, log: Callable[[str], None] | None = None,
                eigene_messpunkte: bool = False) -> dict:
    """Katalog + vollständige Abonnenten-Historie EINER Quelle spiegeln.

    1. Vollkatalog (minSubscribers=0) via ingest.hole_katalog — dieselbe
       validierte Pagination wie „Alle Signale"; katalog_signale wird
       mit-aktualisiert (beide Übersichten teilen sich den Bestand).
    2. je Provider GET /history → subscriber_history (idempotenter Upsert;
       404 = Client kennt keinen Verlauf, dann bleibt die Historie unbekannt).
    Katalogzeilen und selbst ein stabiler Update-Job binden die einzelnen
    Zähler nicht an einen Messzeitpunkt. Daher entstehen keine Eigenpunkte.
    ``eigene_messpunkte`` bleibt nur zur Aufrufkompatibilität angenommen.

    Rückgabe {"anzahl", "history_punkte", "messpunkte", "fehler" (Liste),
    "abgebrochen" (str|None)}. Verbindungs-/Auth-Fehler brechen DIESE Quelle
    ab (weitere Anfragen würden gleichartig scheitern); Einzel fehler
    (z. B. kaputte JSON-Zeile eines Providers) werden gesammelt.
    """
    def _log(text: str) -> None:
        if log:
            log(f"{kuerzel}: {text}")

    db.init_db()
    kuerzel = db.kanonische_quelle(quelle.get("kuerzel") or "")
    eintrag = {"anzahl": 0, "history_punkte": 0, "messpunkte": 0,
               "fehler": [], "abgebrochen": None}
    try:
        client = quellen.client_fuer_quelle(quelle, timeout=_KATALOG_TIMEOUT_S)
        roh = ingest.hole_katalog(quelle, client=client, min_subscribers=0)
    except downloader_client.DownloaderError as exc:
        # Offline/Token/Kaputt: DIESER Quelle abbrechen, die anderen laufen
        # weiter (Muster katalog.sync) — Fehler landet im Summary.
        eintrag["abgebrochen"] = str(exc)
        _log(f"Katalog nicht ladbar — {exc}")
        return eintrag
    zeilen = katalog._normalisiere(roh)
    scope_warning = ingest.katalog_scope_hinweis(roh)
    gespeichert, geloescht = db.katalog_upsert_many(
        quelle["kuerzel"], zeilen, fehlende_loeschen=not scope_warning)
    if scope_warning:
        eintrag["fehler"].append(scope_warning)
        _log(scope_warning)
    eintrag["anzahl"] = gespeichert
    _log(f"Katalog: {gespeichert} Signale übernommen, {geloescht} rausgefallen.")

    for zeile in zeilen:
        signal_id = int(zeile["signal_id"])
        version = str(zeile.get("version") or "")
        punkte: list[dict] = []
        try:
            punkte = client.history(signal_id, version)
        except downloader_client.DownloaderNotFound:
            punkte = []  # Kein nativer Zeitbeleg; keinen Ersatzpunkt erfinden.
        except (downloader_client.DownloaderConnectionError,
                downloader_client.DownloaderAuthError) as exc:
            eintrag["abgebrochen"] = str(exc)
            _log(f"Historie-Abbruch bei #{signal_id} — {exc}")
            break
        except downloader_client.DownloaderError as exc:
            eintrag["fehler"].append(f"#{signal_id}: {exc}")
            continue
        try:
            eintrag["history_punkte"] += db.store_history_points(
                signal_id, version, punkte, quelle=kuerzel)
        except db.IdentityError as exc:
            eintrag["fehler"].append(f"#{signal_id}: {exc}")
            continue
    if eintrag["fehler"]:
        _log(f"{len(eintrag['fehler'])} Einzel fehler bei der Historie.")
    _log(f"Historie gespiegelt: {eintrag['history_punkte']} Punkte, "
         f"{eintrag['messpunkte']} eigene Messpunkte.")
    db.katalog_sync_vermerken(kuerzel, gespeichert,
                              "; ".join(eintrag["fehler"][:3]) or None)
    return eintrag


def sync(log: Callable[[str], None] | None = None,
         kuerzels: list[str] | None = None) -> dict:
    """Stufe A: alle aktiven Quellen (oder Teilmenge) spiegeln.

    Eine ausgefallene Quelle bricht die anderen nicht ab — ihr Fehler
    landet im Summary (Muster katalog.sync). """
    quellen._ensure()
    aktiv = db.list_quellen(nur_aktiv=True)
    if kuerzels:
        erlaubt = {db.kanonische_quelle(k) for k in kuerzels}
        aktiv = [q for q in aktiv if db.kanonische_quelle(q["kuerzel"]) in erlaubt]
    summary = {"quellen": {}, "gesamt": 0}
    for quelle in aktiv:
        eintrag = sync_quelle(quelle, log=log)
        summary["quellen"][str(quelle["kuerzel"])] = eintrag
        summary["gesamt"] += int(eintrag["anzahl"] or 0)
    return summary


# ── Zeilen: Vereinte Messreihen + Katalog-Metadaten + Ampel ───────────────

def zeilen(*, katalog_zeilen=None, history_punkte=None, workflow_zeilen=None,
           ampeln=None, dokumente=None, berichte_zaehler=None) -> list[dict]:
    """Tabellenzeilen der Abonnentenstatistik aus der lokalen DB.

    Basis ist der Katalog (katalog_signale); Identitäten mit Messreihe, aber
    ohne Katalogzeile (z. B. nur über den Workflow gespiegelte MQL5-Signale)
    kommen mit Metadaten aus der signals-Tabelle dazu. Bewertet wird nichts —
    die Ampel-Spalte zeigt das neueste ENGINE-Ergebnis an (reine Anzeige).
    """
    db.init_db()
    katalog_zeilen = db.katalog_list() if katalog_zeilen is None else katalog_zeilen
    history_punkte = db.subscriber_history_alle() if history_punkte is None else history_punkte
    ampeln = db.letzte_ampeln_je_signal() if ampeln is None else ampeln
    dokumente = ({} if dokumente is None else dokumente)
    berichte_zaehler = ({} if berichte_zaehler is None else berichte_zaehler)

    reihen: dict[int, dict[str, list[tuple[datetime, int]]]] = defaultdict(lambda: defaultdict(list))
    identitaeten: dict[int, tuple[str, int]] = {}
    for p in history_punkte:
        ts = _parse_ts(p.get("ts"))
        wert = p.get("subscribers")
        if ts is None or wert is None:
            continue
        try:
            ref = int(p["signal_ref"])
            reihen[ref][str(p["version"])].append((ts, int(wert)))
            identitaeten[ref] = (str(p.get("quelle") or "mql5"),
                                 int(p["signal_id"]))
        except (TypeError, ValueError):
            continue
    for versionen in reihen.values():
        for version in versionen:
            versionen[version] = sorted(versionen[version], key=lambda x: x[0])

    metadaten: dict[int, dict] = {}
    for zeile in katalog_zeilen:
        metadaten[int(zeile["signal_ref"])] = zeile
    if workflow_zeilen is None:
        workflow_zeilen = db.list_catalog()
    _analyse_felder = ("trade_analyse", "risiko_analyse", "gesamtbericht",
                       "tiefenanalyse")
    for zeile in workflow_zeilen:
        ref = zeile.get("signal_ref")
        if ref is None:
            continue
        ref = int(ref)
        if ref not in metadaten:
            metadaten[ref] = zeile
        else:
            # GESCANNNTE Signale haben Katalog- UND Workflow-Zeile — die
            # Katalogzeile trägt keine Analyse-Felder (Bug 20.10.: „Ber."
            # blieb leer, obwohl Tiefenanalysen existierten). Gezielt
            # mergen: nur belegte Analyse-Felder aus der Workflow-Zeile.
            for feld in _analyse_felder:
                if zeile.get(feld):
                    metadaten[ref][feld] = zeile[feld]
    # Messreihen ohne jede Metadaten-Zeile (weder Katalog noch Workflow)
    # erhalten eine Minimalzeile aus ihrer Identität — Messpunkte gehen
    # nie still verloren.
    for ref, (kuerzel, externe) in identitaeten.items():
        if ref not in metadaten:
            metadaten[ref] = {"signal_id": externe, "quelle": kuerzel,
                              "name": None, "platform": "", "version": "",
                              "url": "", "abonnenten": None}

    out: list[dict] = []
    for signal_ref, meta in metadaten.items():
        versionen = reihen.get(signal_ref, {})
        version = str(meta.get("version") or "")
        if version not in versionen and versionen:
            version = max(versionen, key=lambda v: versionen[v][-1][0])
        reihe = versionen.get(version, [])
        zeile = {
            "signal_ref": int(signal_ref),
            "signal_id": int(meta.get("signal_id") or 0),
            "quelle": str(meta.get("quelle") or "mql5"),
            "name": str(meta.get("name") or meta.get("signal_id") or ""),
            "platform": str(meta.get("platform") or ""),
            "version": version,
            "url": str(meta.get("url") or ""),
            "abonnenten": None, "delta_letzt": None,
            "delta_7": None, "delta_7_pct": None, "delta_30": None,
            "stand": None, "messpunkte": len(reihe),
            "verlauf30": [],
            "berichte": len({feld for feld in
                             ("trade_analyse", "risiko_analyse",
                              "gesamtbericht", "tiefenanalyse")
                             if meta.get(feld)}
                            | set(berichte_zaehler.get(int(signal_ref)) or {})),
            "doku": list(dokumente.get(int(signal_ref)) or []),
            "ampel": (ampeln.get(int(signal_ref)) or {}).get("ampel"),
        }
        try:
            katalog_abo = meta.get("abonnenten")
            zeile["abonnenten"] = (int(katalog_abo)
                                   if katalog_abo is not None else None)
        except (TypeError, ValueError, OverflowError):
            pass
        if reihe:
            aktuell_ts, aktuell = reihe[-1]
            zeile["abonnenten"] = aktuell
            zeile["stand"] = aktuell_ts
            if len(reihe) >= 2:
                zeile["delta_letzt"] = aktuell - reihe[-2][1]
            zeile["delta_7"] = _bilanz_reihe(reihe, 7, aktuell)
            zeile["delta_30"] = _bilanz_reihe(reihe, 30, aktuell)
            # Prozentspalte (Nutzer-Wunsch 20.10.): +246 bei 1.400 Abonnenten
            # ist etwas anderes als +5 bei 5 — Basis ist der STAND des
            # 7-Tage-Vergleichspunkts. Basis 0 oder fehlender Punkt: kein
            # Prozentsatz (aus 0 wachsen ist mathematisch undefiniert, die
            # absolute Zahl sagt es dann besser).
            basis7 = _vergleichspunkt(reihe, 7)
            if basis7:
                zeile["delta_7_pct"] = round(
                    (aktuell - basis7) / basis7 * 100.0, 1)
            # Sparkline-Fenster: relativ zum NEUESTEN Punkt (wie MqlDownloader)
            fenster_ab = aktuell_ts - timedelta(days=_SPARKLINE_FENSTER_TAGE)
            zeile["verlauf30"] = [(ts.isoformat(timespec="minutes"), wert)
                                  for ts, wert in reihe if ts >= fenster_ab]
        out.append(zeile)
    return out


# ── Zuwachs-Ampel je Quelle (Nutzer-Wunsch 20.10.): Broker-relativ ─────────
#
# Grundregel: +246 ist bei Pelican normal, bei MQL5 (Ø ~40 Abonnenten)
# unmöglich — die Stufe eines Signals wird deshalb gegen den DURCHSCHNITT
# seiner QUELLE gemessen, nicht absolut. Nur Signale mit mindestens 1
# Abonnent zählen in den Durchschnitt (Nutzer-Regel).
#
# Der Durchschnitt ist GESTUTZT (oberste 5 % der Werte abgeschnitten):
# Verteilungen sind rechtssteil — ein einzelner +1.248-%-Ausreißer würde
# die Latte sonst unerreicherbar legen (Vantage: roh +48,4 %, gestutzt
# +19,7 %). Ist der gestutzte Durchschnitt <= 0 (MQL5: viele kleine
# Konten schwanken prozentual stark nach unten), wird Grün an echtes
# Wachstum gebunden statt an den negativen Schnitt.

_ZUWACHS_TRIMM_ANTEIL = 0.95  # oberste 5 % abschneiden
_STARKER_VERLUST_PCT = -10.0  # >10 % des Bestands in 7 Tagen verloren


def zuwachs_stufen(zeilen: list[dict]) -> dict[str, dict]:
    """Je Quelle: gestutzter Durchschnitt von Δ 7 Tage %.

    Gezählt werden nur Signale mit mindestens 1 Abonnent UND gültigem
    Δ-7-Tage-Prozentwert. Rückgabe {quelle: {"durchschnitt_pct", "anzahl"}}
    — ohne nutzbare Werte: durchschnitt_pct None.
    """
    je_quelle: dict[str, list[float]] = {}
    for zeile in zeilen:
        if (zeile.get("abonnenten") or 0) >= 1 and zeile.get("delta_7_pct") is not None:
            je_quelle.setdefault(str(zeile.get("quelle") or ""), []).append(
                float(zeile["delta_7_pct"]))
    out: dict[str, dict] = {}
    for quelle, werte in je_quelle.items():
        werte.sort()
        kante = max(1, int(len(werte) * _ZUWACHS_TRIMM_ANTEIL))
        out[quelle] = {"durchschnitt_pct": sum(werte[:kante]) / kante,
                       "anzahl": len(werte)}
    return out


def zuwachs_ampel(delta_7_pct, durchschnitt_pct) -> str | None:
    """Broker-relative Stufe des 7-Tage-Zuwachses.

    'gruen' (über dem Broker-Schnitt UND wachsend), 'gelb' (wachsend,
    unter dem Schnitt), 'orange' (leichte Verluste), 'rot' (starker
    Verlust > 10 % des Bestands), None (unverändert 0 oder kein
    Vergleichspunkt — keine Stufe, nie eine falsche Aussage).
    """
    if delta_7_pct is None:
        return None
    if delta_7_pct < _STARKER_VERLUST_PCT:
        return "rot"
    if delta_7_pct < 0:
        return "orange"  # auch "über Ø" — Verlierer sind nie grün (MQL5-Fall)
    if delta_7_pct == 0:
        return None
    # Ab hier wachsend: grün, sobald der Broker-Schnitt erreicht/übertroffen
    # ist — bei negativem Schnitt (MQL5) zählt damit JEDES Wachstum als grün,
    # weil es dort bereits überdurchschnittlich ist.
    schnitt = durchschnitt_pct if durchschnitt_pct is not None else 0.0
    if delta_7_pct >= schnitt:
        return "gruen"
    return "gelb"


def mit_zuwachs_ampel(zeilen: list[dict]) -> dict[str, dict]:
    """Jeder Zeile 'zuwachs_ampel' + 'quelle_durchschnitt_pct' anreichern.

    Bewertet wird nichts — die Stufe ist eine reine Gruppierung des
    gemessenen Zuwachses gegen den Quelle-Schnitt. Rückgabe: die
    Stufen-Statistik je Quelle (für Legende/KPI).
    """
    stufen = zuwachs_stufen(zeilen)
    for zeile in zeilen:
        statistik = stufen.get(str(zeile.get("quelle") or ""))
        zeile["quelle_durchschnitt_pct"] = (
            statistik["durchschnitt_pct"] if statistik else None)
        zeile["zuwachs_ampel"] = zuwachs_ampel(
            zeile.get("delta_7_pct"), zeile["quelle_durchschnitt_pct"])
    return stufen


# ── Hintergrund-Refresh (Stufe A / Stufe B) ───────────────────────────────

_REFRESH_LOCK = threading.Lock()
_REFRESH: dict = {"laeuft": False}


def refresh_laeuft() -> bool:
    with _REFRESH_LOCK:
        return bool(_REFRESH.get("laeuft"))


def refresh_zustand() -> dict:
    with _REFRESH_LOCK:
        return copy.deepcopy(_REFRESH)


def refresh_anzeige(zustand: dict, *, jetzt: datetime | None = None) -> dict:
    """Ordnet einen Refreshbeleg zeitlich ein; fragt keinen aktuellen Client ab.

    Neue Abschlussmeldungen bleiben zunächst aufgeklappt. Ältere Belege sind
    weiterhin sichtbar und abrufbar, aber keine vermeintliche Livefehlermeldung.
    Ein undatierter Altbeleg wird sicherheitshalber nicht automatisch eingeklappt.
    """
    summary = zustand.get("summary") or {}
    errors = bool(zustand.get("fehler") or any(
        item.get("fehler") or item.get("abgebrochen")
        for item in (summary.get("quellen") or {}).values()))
    status = ("läuft" if zustand.get("laeuft") else
              "abgebrochen" if zustand.get("stopp") else
              "mit Fehlern beendet" if errors else
              "erfolgreich beendet" if isinstance(zustand.get("summary"), dict) else
              "ohne Ergebnisbeleg beendet")
    start, end = zustand.get("gestartet"), zustand.get("beendet")
    # Legacyzustände laufen eventuell noch in einem bereits gestarteten Prozess.
    # Für deren einmalige UI-Übernahme reicht eine stabile Belegkennung.
    key = str(zustand.get("lauf_id") or f"alt:{start or '?'}:{end or '?'}")
    fresh = True
    if end:
        try:
            stamp = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
            current = jetzt or datetime.now().astimezone()
            if stamp.tzinfo is None:
                stamp = stamp.astimezone()
            if current.tzinfo is None:
                current = current.astimezone()
            age = (current - stamp).total_seconds()
            fresh = age <= 15 * 60
        except (ValueError, TypeError):
            pass
    return {"kennung": key, "status": status, "frisch": fresh,
            "gestartet": str(start or "Zeitpunkt unbekannt"),
            "beendet": str(end or "Zeitpunkt unbekannt")}


def stoppe_refresh() -> None:
    with _REFRESH_LOCK:
        if _REFRESH.get("laeuft"):
            _REFRESH["stopp"] = True


def starte_refresh(*, messen: bool, kuerzels: list[str] | None = None,
                   bereit_warten_s: float = 60.0, poll_s: float = 5.0) -> bool:
    """Refresh im Hintergrund-Thread starten. False, wenn bereits einer läuft.

    messen=False → Stufe A (nur lesen). messen=True → Stufe B zuerst bei den
    gewählten Quellen frisch messen (tradelisten=False, katalogMaxAlterH=0),
    danach immer Stufe A über ALLE aktiven Quellen.
    """
    with _REFRESH_LOCK:
        if _REFRESH.get("laeuft"):
            return False
        _REFRESH.clear()
        _REFRESH.update({"laeuft": True, "fertig": False, "stopp": False,
                         "lauf_id": "abo-" + uuid4().hex,
                         "messen": bool(messen), "phase": "",
                         "quellen": {}, "logs": [], "summary": None,
                         "fehler": "", "gestartet": datetime.now().astimezone().isoformat(
                             timespec="seconds")})

    def _log(text: str) -> None:
        with _REFRESH_LOCK:
            _REFRESH["logs"] = (list(_REFRESH.get("logs") or []) + [text])[-200:]

    def _fortschritt(z: dict) -> None:
        with _REFRESH_LOCK:
            _REFRESH.setdefault("quellen", {})[str(z.get("kuerzel"))] = z

    def _arbeit() -> None:
        try:
            client_ergebnisse = {}
            if messen:
                with _REFRESH_LOCK:
                    _REFRESH["phase"] = "clients"
                from . import client_updates
                client_ergebnisse = client_updates.starte_alle_updates(
                    config.load_settings(), log=_log, on_fortschritt=_fortschritt,
                    gestopft=lambda: bool(_REFRESH.get("stopp")),
                    tradelisten=False, katalog_max_alter_h=0.0,
                    quellen_filter=kuerzels, modus="abonnenten",
                    bereit_warten_s=bereit_warten_s, poll_s=poll_s)
            with _REFRESH_LOCK:
                if _REFRESH.get("stopp"):
                    _REFRESH["phase"] = "abgebrochen"
                    return
                _REFRESH["phase"] = "lesen"
            summary = sync(log=_log)
            for kuerzel, ergebnis in client_ergebnisse.items():
                coverage = ergebnis.get("abonnenten_katalog") or {}
                if ergebnis.get("abonnenten_auswahl_unbestaetigt") is True:
                    eintrag = summary["quellen"].setdefault(kuerzel, {"anzahl": 0, "fehler": []})
                    eintrag["abonnenten_auswahl_unbestaetigt"] = True
                    eintrag.setdefault("fehler", []).append(
                        "Auswahl unbestätigt: " + str(ergebnis.get("detail") or "Auswahlbeleg fehlt"))
                elif (ergebnis.get("status") == client_updates.TEILWEISE
                        and coverage.get("complete") is False):
                    eintrag = summary["quellen"].setdefault(kuerzel, {"anzahl": 0, "fehler": []})
                    eintrag["abonnenten_katalog"] = coverage
                    eintrag.setdefault("fehler", []).append(
                        "Auswahl mit Kataloglücken: " + str(ergebnis.get("detail") or "API-Positionen ausgelassen"))
                elif ergebnis.get("status") != client_updates.FERTIG:
                    eintrag = summary["quellen"].setdefault(kuerzel, {"anzahl": 0, "fehler": []})
                    eintrag.setdefault("fehler", []).append(
                        "Frischmessung fehlgeschlagen: " + str(
                            ergebnis.get("fehler") or ergebnis.get("detail") or ergebnis.get("status")))
            with _REFRESH_LOCK:
                _REFRESH["summary"] = summary
        except Exception as exc:  # Der Thread darf die GUI nie mitreißen.
            with _REFRESH_LOCK:
                _REFRESH["fehler"] = f"{type(exc).__name__}: {exc}"
                fehler = _REFRESH["fehler"]
            _log(f"Refresh fehlgeschlagen — {fehler}")
        finally:
            with _REFRESH_LOCK:
                _REFRESH["laeuft"] = False
                _REFRESH["fertig"] = True
                _REFRESH["phase"] = ""
                _REFRESH["beendet"] = datetime.now().astimezone().isoformat(timespec="seconds")

    threading.Thread(target=_arbeit, name="abonnenten-refresh",
                     daemon=True).start()
    return True
