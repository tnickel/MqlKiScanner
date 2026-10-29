# -*- coding: utf-8 -*-
"""Ingest: Signale aus Datenquellen-REST abholen (Konzept doc/20, Stufe 1).

Je aktiver Quelle (Typ `mql5-downloader-v1`) werden geholt und gecacht:
- Katalog (`GET /providers`, paginiert) → Kandidaten im Pipeline-Format
- Trades (`GET /providers/{id}/{v}/trades.csv`) → Original-mql5-CSV, per
  SHA gegen `quellen_artefakte` unveränderte Dateien werden nicht erneut
  verarbeitet (Delta-Prinzip wie beim Betreuer-Agenten)
- Metrics (`GET /providers/{id}/{v}/metrics`) → Kennzahlen als Ersatz für
  die wegfallende MQL5-Kennzahlenseite

Bewertet wird hier nichts — die Forensik rechnet weiter selbst aus der
Trades-CSV (Design-Regel 1: Code rechnet, LLM interpretiert). Fehlende
Werte (z. B. Initial Deposit bis zur Downloader-Erweiterung) bleiben
ehrlich None statt geraten.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
import threading
from functools import wraps

from pathlib import Path

from . import config, db, downloader_client, quellen

_PLATTFORM = {"mql4": "mt4", "mql5": "mt5", "pelican": "pelican",
              "vantage": "vantage", "zulu": "zulu"}
_KUERZEL_SICHER = re.compile(r"[^A-Za-z0-9_\-]")
_ARTEFAKT_LOCKS: dict[tuple, threading.RLock] = {}
_ARTEFAKT_LOCKS_GUARD = threading.Lock()


def _serialisiere_artefakt(fn):
    """Coordinate each artifact's file and DB entry across threads/clients."""
    @wraps(fn)
    def wrapped(quelle, signal_id, version, *args, **kwargs):
        key = (str(config.DATA_DIR.resolve()), int(quelle['id']),
               int(signal_id), str(version), fn.__name__)
        with _ARTEFAKT_LOCKS_GUARD:
            lock = _ARTEFAKT_LOCKS.setdefault(key, threading.RLock())
        with lock:
            return fn(quelle, signal_id, version, *args, **kwargs)
    return wrapped


def _version_sicher(version: str) -> str:
    """version-Segment für Cache-Dateinamen sanitisieren.

    version kommt UNVERÄNDERT aus dem Katalog der Fremdquelle (LAN-HTTP) —
    ein „../../x" wäre Path-Traversal: Der Cache-Pfad würde AUSSERHALB von
    data/quellen/<kuerzel>/ landen (Review 29.09., D). Gleiches Muster wie
    beim Kürzel: alles außer [A-Za-z0-9_-] → Unterstrich. Die Plattform-
    Versionen (mql4/mql5/pelican/…) bleiben unberührt.
    """
    return _KUERZEL_SICHER.sub("_", str(version or "mql5"))


def _kuerzel_verzeichnis(quelle: dict):
    """Stable owner directory; display aliases must never determine ownership.

    Existing artifact records retain their stored paths and remain readable.
    A legacy/synthetic dict without a UID receives an explicitly unverified
    deterministic path, never an invented registry identity or DB registration.
    """
    uid = quelle.get("quellen_uid")
    if uid:
        name = "owner-" + hashlib.sha256(str(uid).encode("utf-8")).hexdigest()
    else:
        fallback = json.dumps({key: quelle.get(key) for key in ("id", "kuerzel", "base_url")},
                              ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        name = "unverified-" + hashlib.sha256(fallback).hexdigest()
    verzeichnis = config.DATA_DIR / "quellen" / name
    verzeichnis.mkdir(parents=True, exist_ok=True)
    return verzeichnis


class KatalogListe(list):
    """Paginated rows retain the source's actual catalog scope receipt."""
    def __init__(self, items=(), *, catalog_scope=None):
        super().__init__(items)
        self.catalog_scope = catalog_scope


def katalog_scope(items) -> str | None:
    return getattr(items, "catalog_scope", None)


def katalog_scope_hinweis(items) -> str:
    if katalog_scope(items) == "full":
        return ""
    if katalog_scope(items) == "unknown":
        return ("Vollkatalog nicht bestätigt: catalogScope=unknown (Listenbasis unbelegt). "
                "Vorhandene Kataloganbieter bleiben erhalten.")
    return ("Vollkatalog nicht bestätigt: Quelle liefert nur die Abonnentenauswahl. "
            "Vorhandene Kataloganbieter bleiben erhalten." if katalog_scope(items) == "subscribers" else
            "Vollkatalog nicht bestätigt: catalogScope fehlt. Quelle aktualisieren; "
            "vorhandene Kataloganbieter bleiben erhalten.")


def hole_katalog(quelle: dict, *, client: downloader_client.DownloaderClient | None = None,
                 seitengroesse: int = 500, max_seiten: int = 100,
                 min_subscribers: int = 1, catalog_scope: str = "full") -> list[dict]:
    """Validate pagination and retain the separate actual list-scope receipt.

    ``total`` zählt Rohzeilen vor der Normalisierung. Eine Teilantwort darf
    nie als Vollkatalog fehlende IDs aus ``katalog_signale`` löschen. Even
    complete pagination permits replacement only with catalog_scope=full.
    Vollständigkeit gilt für den gewählten Abonnenten-Scope: reguläre
    Kandidaten behalten 1; die Übersicht fordert ausdrücklich 0 an.
    """
    cli = client or quellen.client_fuer_quelle(quelle)
    if catalog_scope not in {"full", "subscribers"}:
        raise ValueError("catalog_scope muss full oder subscribers sein")
    items: list[dict] = []
    offset = 0
    gesamt = None
    gesehen = set()
    page_scope = None
    for _ in range(max(1, max_seiten)):
        seite = cli.katalog(limit=seitengroesse, offset=offset,
                           min_subscribers=min_subscribers, catalog_scope=catalog_scope)
        if not isinstance(seite, dict) or not isinstance(seite.get("items"), list):
            raise downloader_client.DownloaderError("Katalog unvollständig: ungültige Seite/items.")
        block = seite["items"]
        actual_scope = seite.get("catalogScope")
        if actual_scope is not None and (not isinstance(actual_scope, str) or actual_scope not in {"full", "subscribers", "unknown"}):
            raise downloader_client.DownloaderError("Katalog unvollständig: ungültiger catalogScope.")
        if gesamt is not None and actual_scope != page_scope:
            raise downloader_client.DownloaderError("Katalog unvollständig: catalogScope wechselte während der Pagination.")
        page_scope = actual_scope
        raw_total = seite.get("total")
        try:
            if isinstance(raw_total, bool):
                raise ValueError
            total = int(str(raw_total).strip())
            if total < 0:
                raise ValueError
        except (TypeError, ValueError, OverflowError) as exc:
            raise downloader_client.DownloaderError(
                "Katalog unvollständig: gültige Gesamtzahl total fehlt.") from exc
        if gesamt is not None and total != gesamt:
            raise downloader_client.DownloaderError(
                f"Katalog unvollständig: Gesamtzahl änderte sich von {gesamt} auf {total}.")
        gesamt = total
        if "offset" in seite and seite["offset"] != offset:
            raise downloader_client.DownloaderError(
                f"Katalog unvollständig: fremder Seitenoffset statt {offset}.")
        if offset + len(block) > total:
            raise downloader_client.DownloaderError("Katalog unvollständig: mehr Rohzeilen als total.")
        for item in block:
            if not isinstance(item, dict):
                raise downloader_client.DownloaderError("Katalog unvollständig: ungültiger Eintrag.")
            identitaet = (str(item.get("signalId", "")).strip(),
                          str(item.get("version", "")).strip())
            if identitaet in gesehen:
                raise downloader_client.DownloaderError(
                    "Katalog unvollständig: wiederholte Signal-/Versionsidentität.")
            gesehen.add(identitaet)
        items.extend(block)
        offset += len(block)
        if offset == total:
            return KatalogListe(items, catalog_scope=page_scope)
        if not block:
            raise downloader_client.DownloaderError(
                f"Katalog unvollständig: leere Seite nach {offset} von {total} Rohzeilen.")
    raise downloader_client.DownloaderError(
        f"Katalog unvollständig: Seitenlimit erreicht ({offset} von {gesamt} Rohzeilen).")


def normalisiere_wochen(wert) -> float | None:
    """An age is proven only by a finite, nonnegative number, never a bool."""
    if wert is None or isinstance(wert, bool):
        return None
    try:
        zahl = float(wert)
    except (TypeError, ValueError, OverflowError):
        return None
    return zahl if math.isfinite(zahl) and zahl >= 0 else None


def normalisiere_abonnenten(wert) -> int | None:
    """Missing or invalid counts do not prove an audience; zero is known zero."""
    zahl = normalisiere_wochen(wert)
    return int(zahl) if zahl is not None and zahl.is_integer() else None


def kandidaten(quelle: dict, items: list[dict]) -> list[dict]:
    """Katalog-Items → Kandidaten im Pipeline-Format (crawler-Kompatibel).

    `wochen` ist ohne Quellbeleg unbekannt (None) — der Wochen-Vorfilter
    lehnt das regulär ab; Fix-IDs können den Vorfilter umgehen.
    `quelle_kuerzel`/`quelle_id`/`quelle_version` steuern später den
    Trade-Bezug aus dem Quellen-Cache statt über den MQL5-Exporter.
    """
    out = []
    for item in items:
        try:
            signal_id = int(str(item.get("signalId", "")).strip())
        except ValueError:
            continue
        version = str(item.get("version") or "").strip()
        # Quellen liefern belegtes Alter (weeks), etwa aus ihrem Profilcache.
        # Ohne Altersbeleg bleibt der Kandidat unbekannt; der Vorfilter
        # wird dadurch weder deaktiviert noch mit einem Ersatzwert umgangen.
        wochen = normalisiere_wochen(item.get("weeks"))
        out.append({
            "id": signal_id,
            "name": str(item.get("signalName") or str(signal_id)),
            "platform": _PLATTFORM.get(version, ""),
            "url": str(item.get("url")
                       or f"https://www.mql5.com/en/signals/{signal_id}"),
            "abonnenten": normalisiere_abonnenten(item.get("subscribers")),
            "wochen": wochen,
            "quelle_kuerzel": str(quelle.get("kuerzel") or ""),
            "quelle_id": int(quelle["id"]),
            "quellen_uid": str(quelle.get("quellen_uid") or ""),
            "quelle_version": version,
        })
    return out


def kandidaten_aus_quellen(log=None) -> list[dict]:
    """Kandidaten aller aktiven Quellen, sequenziell; erste Quelle gewinnt
    bei Doppelung (dieselbe MQL5-ID in mehreren Spiegeln = dasselbe Signal)."""
    def _log(text: str) -> None:
        if log:
            log(text)

    quellen._ensure()
    aktiv = db.list_quellen(nur_aktiv=True)
    if not aktiv:
        _log("Keine aktive Datenquelle konfiguriert (Admin → Datenquellen).")
        return []
    out: list[dict] = []
    gesehen: set[tuple[int, str]] = set()
    for quelle in aktiv:
        try:
            items = hole_katalog(quelle)
            if katalog_scope(items) != "full":
                _log(f"Quelle {quelle['kuerzel']}: Workflow übersprungen — {katalog_scope_hinweis(items)}")
                continue
        except downloader_client.DownloaderError as exc:
            _log(f"Quelle {quelle['kuerzel']}: Katalog nicht erreichbar — {exc}")
            continue
        neu = 0
        for kandidat in kandidaten(quelle, items):
            from .signal_identity import key_for
            # Keep contradictory platforms until the source-scoped conflict
            # check in build_candidates; first-row wins would hide the error.
            key = (key_for(kandidat), str(kandidat.get("platform") or "").upper().replace("MQL", "MT"),
                   str(kandidat.get("quelle_version") or "").lower())
            if key in gesehen:
                continue
            gesehen.add(key)
            out.append(kandidat)
            neu += 1
        _log(f"Quelle {quelle['kuerzel']}: {len(items)} Katalog-Einträge, "
             f"{neu} neue Kandidaten (gesamt {len(out)}).")
    # Wie crawl_lists: absteigend nach Abonnenten. Die Reihenfolge entscheidet
    # spaeter, wen top_n_export (Forensik-Export) trifft — unsortiert haette
    # der Katalog eines Downloader-Defaults "aufsteigend" die KLEINSTEN
    # Provider zuerst geliefert (Review MqlDownloader 28.09.2026).
    out.sort(key=lambda s: (-(s.get("abonnenten") or 0), s["id"]))
    return out


@_serialisiere_artefakt
def hole_trades(quelle: dict, signal_id: int, version: str, *,
                client: downloader_client.DownloaderClient | None = None,
                allow_offline_cache: bool = True) -> tuple[str, bool]:
    """Trades-CSV holen und SHA-gespiegelt cachen. Rückgabe (Pfad, geändert).

    Offline-Fallback (Nutzer-Fall 02.10.: Teilscan bei offline Quelle):
    Scheitert der Abruf (Verbindung), wird das letzte gecachte Artefakt
    geliefert (geändert=False) — der Teilscan prüft dann den BEKANNTEN
    Stand weiter, statt die DB-🟢/🟡 still zu überspringen."""
    cli = client or quellen.client_fuer_quelle(quelle)
    try:
        roh = cli.trades_csv(signal_id, version)
    except downloader_client.DownloaderConnectionError:
        if not allow_offline_cache:
            raise
        alt_offline = db.get_quellen_artefakt(int(quelle["id"]), signal_id,
                                              version, "trades")
        if alt_offline and alt_offline.get("path") \
                and Path(alt_offline["path"]).exists():
            # B5 (Lauf-Review 02.10.): Auch offline NUR bei intaktem Inhalt —
            # dieselbe SHA-Prüfung wie beim Cache-Treffer. Eine veränderte
            # Datei (falscher Hash) ist KEIN belastbarer Bekannter Stand,
            # sondern ein vergifteter Cache: ehrlich scheitern statt still
            # falsche Forensik rechnen.
            try:
                if alt_offline.get("sha256") == hashlib.sha256(
                        Path(alt_offline["path"]).read_bytes()).hexdigest():
                    return str(alt_offline["path"]), False
                raise downloader_client.DownloaderConnectionError(
                    f"Quelle offline und Cache verändert (SHA weicht ab): "
                    f"{alt_offline['path']} — Artefakt nicht belastbar.")
            except OSError as exc:
                raise downloader_client.DownloaderConnectionError(
                    f"Quelle offline und Cache unlesbar: {exc}") from exc
        raise
    sha = hashlib.sha256(roh).hexdigest()
    alt = db.get_quellen_artefakt(int(quelle["id"]), signal_id, version, "trades")
    if alt and alt.get("sha256") == sha and alt.get("path") \
            and Path(alt["path"]).exists():
        # Cache-Treffer nur bei INTAKTER Datei: Der Inhalt wird gegen den
        # SHA geprüft — eine nachträglich korrumpierte Datei wäre sonst die
        # unvermerkte Grundlage der Forensik (Review 29.09.).
        try:
            if hashlib.sha256(Path(alt["path"]).read_bytes()).hexdigest() == sha:
                return str(alt["path"]), False
        except (OSError, ValueError):
            # Übergabe-Review 01.10.: symmetrisch zu hole_metrics — ValueError
            # deckt Dekodier-/JSON-Fehler ab, OSError Lese-/Sperrfehler.
            pass  # unlesbar: unten neu schreiben
    pfad = _kuerzel_verzeichnis(quelle) / f"{_version_sicher(version)}_{int(signal_id)}_trades.csv"
    _atomar_schreiben(pfad, roh)
    db.store_quellen_artefakt(int(quelle["id"]), signal_id, version,
                              "trades", sha, str(pfad))
    return str(pfad), True


@_serialisiere_artefakt
def hole_metrics(quelle: dict, signal_id: int, version: str, *,
                 client: downloader_client.DownloaderClient | None = None,
                 allow_offline_cache: bool = True) -> dict:
    """Metrics-Antwort holen und cachen; Rückgabe ist das gecachte JSON.

    Offline-Fallback wie hole_trades: Verbindung fehlgeschlagen + Cache
    vorhanden → letzter bekannter Stand (geändert=False logisch).
    Ein neu benötigter Währungsnachweis kann diesen Fallback ausschalten.
    """
    cli = client or quellen.client_fuer_quelle(quelle)
    try:
        antwort = cli.metrics(signal_id, version)
    except downloader_client.DownloaderConnectionError:
        if not allow_offline_cache:
            raise
        alt_offline = db.get_quellen_artefakt(int(quelle["id"]), signal_id,
                                              version, "metrics")
        if alt_offline and alt_offline.get("path") \
                and Path(alt_offline["path"]).exists():
            # B5 (Lauf-Review 02.10.): Offline nur bei intaktem Inhalt —
            # SHA der Datei gegen den gespeicherten Vermerk prüfen (dieselbe
            # Kanonisierung wie beim Schreiben: sort_keys/indent/default=str).
            try:
                inhalt = Path(alt_offline["path"]).read_bytes()
                if alt_offline.get("sha256") != hashlib.sha256(inhalt).hexdigest():
                    raise downloader_client.DownloaderConnectionError(
                        "Quelle offline und Metrics-Cache verändert "
                        "(SHA weicht ab) — Artefakt nicht belastbar.")
                return json.loads(inhalt.decode("utf-8"))
            except downloader_client.DownloaderError:
                raise
            except (OSError, ValueError) as exc:
                raise downloader_client.DownloaderConnectionError(
                    f"Quelle offline und Metrics-Cache unlesbar: {exc}") from exc
        raise
    # Kanonische Serialisierung: Der SHA beschreibt EXAKT die geschriebenen
    # Bytes (früher: SHA über sort_keys, Datei über indent OHNE sort_keys —
    # der gespeicherte SHA stimmte nie mit der Datei; Review 29.09.).
    roh = json.dumps(antwort, ensure_ascii=False, sort_keys=True,
                     indent=1, default=str).encode("utf-8")
    sha = hashlib.sha256(roh).hexdigest()
    alt = db.get_quellen_artefakt(int(quelle["id"]), signal_id, version, "metrics")
    if alt and alt.get("sha256") == sha and alt.get("path") \
            and Path(alt["path"]).exists():
        try:
            inhalt = Path(alt["path"]).read_bytes()
            if hashlib.sha256(inhalt).hexdigest() == sha:
                return json.loads(inhalt.decode("utf-8"))
        except (OSError, ValueError):
            # JSONDecodeError/UnicodeDecodeError sind ValueError-Unterklassen —
            # ein Satz für beide Caches (Übergabe-Review 01.10.).
            pass  # defekter/korrumpierter Cache: neu schreiben (unten)
    pfad = _kuerzel_verzeichnis(quelle) / f"{_version_sicher(version)}_{int(signal_id)}_metrics.json"
    _atomar_schreiben(pfad, roh)
    db.store_quellen_artefakt(int(quelle["id"]), signal_id, version,
                              "metrics", sha, str(pfad))
    return antwort


def _atomar_schreiben(pfad: Path, daten: bytes) -> None:
    """Übergabe-Review 01.10. (Low 2): Cache-Datei atomar schreiben —
    write_bytes + DB-Eintrag waren nicht atomar; ein Abbruch dazwischen
    hinterließ eine halbierte Datei als mögliche Forensik-Grundlage.
    tmp + replace (gleiche Partition) macht den Pfad nur mit vollständigen
    Bytes sichtbar. Eindeutige Tempdateien und die artefaktbezogene Sperre
    koordinieren parallele Threads inklusive DB-Vermerk."""
    pfad.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=pfad.name + '.', suffix='.tmp', dir=pfad.parent)
    os.close(fd)
    tmp = Path(name)
    try:
        tmp.write_bytes(daten)
        os.replace(tmp, pfad)
    finally:
        tmp.unlink(missing_ok=True)


def _zahl(wert):
    """Quellen-Wert robust in float|None — Monitore liefern teils Strings
    mit deutschem Dezimalkomma (realer Fall 04.10.: EquityDrawdown '9,10'
    aus dem MqlDownloader crashte scoring mit ValueError). Unparsebares
    bleibt None statt die ganze Forensik zu werfen."""
    if wert is None or isinstance(wert, bool):
        return None
    if isinstance(wert, (int, float)):
        return float(wert)
    text = str(wert).strip().replace("\u2212", "-").replace(" ", "")
    if not text:
        return None
    try:
        # Komma als Dezimaltrenner (deutsches Format), Punkt bleibt Punkt;
        # Tausenderpunkte vor Komma werden mitgenommen.
        if "," in text and "." not in text:
            text = text.replace(",", ".")
        else:
            text = text.replace(".", "").replace(",", ".") if "," in text else text
        return float(text)
    except ValueError:
        return None


def _anzahl(wert):
    """Source counts must be finite, non-negative whole numbers."""
    import math
    zahl = _zahl(wert)
    return int(zahl) if zahl is not None and math.isfinite(zahl) and zahl >= 0 and zahl.is_integer() else None


# Broker-Fallback je Quellen-Version (06.10.2026): Monitore, die in metrics
# KEIN "Broker"-Feld liefern (Vantage/Zulu), handeln an der Börse ihres
# Anbieters — Vantage-Copy-API-Konten laufen bei Vantage, CopyFX bei
# RoboForex. Diese Kanonisierung schaltet broker-abhängige Kontraktspecs
# frei (MSFT: Vantage 1 vs. RoboForex 100 USD/Punkt — bewiesen 06.10.).
# pelican/mql5 liefern den echten Server je Signal und brauchen keinen
# Fallback.
# 08.10.2026, Arbeitslisten-Befund: Der RoboMonitor antwortet mit version
# 'mql4' (23 Signale) ODER 'mql5' (7 CopyFX-MT5-Signale) — 'robo' kommt in
# der Antwort NICHT vor, der Fallback griff deshalb fuer RoboForex nie.
# 'mql5' ist Mehrdeutig (auch MqlDownloader-Direkt), deshalb zusaetzlich
# der Fallback ueber das QUELLEN-KUERZEL des Aufrufers (metrics_zu_stats-
# Parameter), der fuer beide Robo-Exportversionen greift.
QUELLEN_BROKER_FALLBACK = {
    "vantage": "vantage",
    "vant": "vantage",
    "robo": "roboforex",
    "zulu": "zulu",
}


def metrics_zu_stats(antwort: dict | None, quelle_kuerzel: str | None = None,
                     *, quelle_version: str | None = None) -> dict:
    """Metrics-Antwort → Felder der MQL5-Kennzahlenseite (doc/20 §4).

    Nur vorhanden Werte werden gemappt — nichts geraten. `initial_deposit_usd`
    greift automatisch, sobald der Downloader es liefert (bis dahin None und
    die Kapitalbasis-Regel ruht für Quellen-Signale). `quelle_kuerzel` ist
    der Broker-Fallback zweiter Stufe (siehe QUELLEN_BROKER_FALLBACK).
    """
    antwort = antwort or {}
    metrics = antwort.get("metrics") if isinstance(antwort.get("metrics"), dict) else {}
    # MqlDownloader exports native account money. The other bundled monitors
    # normalize their CSV and balance to USD. An arbitrary source alias or the
    # transport protocol alone never establishes a USD contract (Robo also uses
    # mql4/mql5 version names). Pelican's Currency describes the original
    # account, whereas its successful CSV and money metrics are already USD.
    # Robo (Nutzer-Freigabe 29.10.2026): erkannt am KÜRZEL, nicht an der
    # Version — CopyFX-PnL ist USD, Zehntel-Lots ×10 bewiesen (6544ef7).
    normalizes_usd = (str(quelle_version or antwort.get("version") or "").lower()
                      in {"pelican", "vantage", "zulu"}
                      or str(quelle_kuerzel or "").strip().lower() == "robo")
    currency = (str(metrics["Currency"]).strip().upper()
                if metrics.get("Currency") is not None else None)
    if normalizes_usd:
        currency = "USD"
    native_money = not normalizes_usd
    eq_dd = _zahl(metrics.get("EquityDrawdown"))
    if eq_dd is None:
        eq_dd = _zahl(metrics.get("MaxDDGraphic"))
    return {
        "dd_equity_pct": eq_dd,
        "dd_balance_pct": None,
        "monthly_growth_pct": _zahl(metrics.get("Average3MonthProfit")),
        "subscribers": metrics.get("Subscribers"),
        "account_currency": currency,
        "initial_deposit_account": _zahl(metrics.get("InitialDeposit")) if native_money else None,
        "balance_account": _zahl(metrics.get("Balance")) if native_money else None,
        "initial_deposit_usd": _zahl(metrics.get("InitialDeposit")) if currency == "USD" else None,
        # Virtuelle Kapitalbasis (z. B. PelicanMonitor "InitialDepositVirtual"):
        # klar markierte Annahme, KEIN Plattformwert. Dient als Fallback fuer
        # die Forensik (DD-/Schock-Prozente brauchen ein Startkapital), nie
        # als echtes InitialDeposit und nie in den Cent-genauen Abgleich.
        "kapitalbasis_virtual_usd": (_zahl(metrics.get("InitialDepositVirtual"))
                                    if currency == "USD" else None),
        # Review 04.10. (V2a-Folge): Vantage kappen Batch-Downloads auf 2.000
        # Trades — der Monitor legt offen, ob die Historie unvollstaendig ist
        # (TradesTruncated / TradesTotalAvailable). Nur Hinweis, kein Malus.
        "quelle_trades_gekappt": metrics.get("TradesTruncated"),
        "quelle_trades_total_available": metrics.get("TradesTotalAvailable"),
        "quelle_trades_stored": _zahl(metrics.get("TradesStored")),
        # Paging/end-of-history evidence is distinct from UTC/identity
        # integrity (TradeHistoryComplete) and from platform-wide totals.
        "quelle_trades_history_complete": metrics.get("TradesHistoryComplete"),
        "quelle_trades_completeness_note": str(metrics.get("TradesCompletenessNote")
                                               or metrics.get("CompletenessNote") or ""),
        "quelle_trade_history_complete": metrics.get("TradeHistoryComplete"),
        "quelle_trade_history_quality_reasons": metrics.get("TradeHistoryQualityReasons") or [],
        # Source aggregates are evidence for retrying an empty cache, not
        # proof of the number of exported positions (e.g. capped histories).
        # Keep them separate from parser.plattform_positions / stats.trades.
        "quelle_trades_anzahl": _anzahl(metrics.get("Trades")),
        "quelle_gewinne_anzahl": _anzahl(metrics.get("Wins")),
        "quelle_verluste_anzahl": _anzahl(metrics.get("Losses")),
        "balance_usd": _zahl(metrics.get("Balance")) if currency == "USD" else None,
        # Vom Datenquellen-Monitor aus der VOLLEN Trade-Kurve nachgemessener
        # Max-EQ-DD (TradeEqDrawdownPct) — unabhängige Zweitmessung neben dem
        # gemeldeten Plattform-DD. Geht seit B1 (Intensiv-Review 29./30.09.)
        # als fünftes Maximum in die Drawdown-Schranke.
        # None = Monitor hat keinen Wert (Trades nie/nicht berechenbar geladen).
        "monitor_trade_eq_dd_pct": _zahl(metrics.get("TradeEqDrawdownPct")),
        # Broker-Kennung des Providers (B6, Intensiv-Review): häufigster
        # ServerCode über die Trades (z. B. PelicanMonitor metrics "Broker").
        # Entscheidet cross_broker=false-Specs (USOIL: 1 vs. 100 Barrel/Lot!).
        # Fallback (06.10.2026): Vantage-/Zulu-Monitor liefern KEIN Broker-
        # Feld — dort ist der Broker durch die QUELLE bestimmt (Vantage-
        # Copy-API-Konten laufen bei Vantage, ZuluTrade-Provider bei ihren
        # Zulu-Brokern, CopyFX bei RoboForex). Pelican-Monitor nennt den
        # echten Server je Signal und gewinnt; mql5 liefert ihn von der
        # Signalseite. Ohne beide bleibt None (Specs mit cross_broker=true
        # greifen weiterhin).
        "broker_server": (metrics.get("Broker")
                          or QUELLEN_BROKER_FALLBACK.get(
                              str(quelle_kuerzel or "").strip().lower())
                          or QUELLEN_BROKER_FALLBACK.get(
                              str(antwort.get("version") or "").lower())),
        "stats_quelle": "datenquelle_metrics",
    }
