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
import re

from pathlib import Path

from . import config, db, downloader_client, quellen

_PLATTFORM = {"mql4": "mt4", "mql5": "mt5", "pelican": "pelican",
              "vantage": "vantage", "zulu": "zulu"}
_KUERZEL_SICHER = re.compile(r"[^A-Za-z0-9_\-]")


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
    kuerzel = _KUERZEL_SICHER.sub("_", str(quelle.get("kuerzel") or "quelle"))
    verzeichnis = config.DATA_DIR / "quellen" / kuerzel
    verzeichnis.mkdir(parents=True, exist_ok=True)
    return verzeichnis


def hole_katalog(quelle: dict, *, client: downloader_client.DownloaderClient | None = None,
                 seitengroesse: int = 500, max_seiten: int = 100) -> list[dict]:
    """Gesamten Katalog einer Quelle (paginiert) als Roh-Items holen."""
    cli = client or quellen.client_fuer_quelle(quelle)
    items: list[dict] = []
    offset = 0
    for _ in range(max(1, max_seiten)):
        seite = cli.katalog(limit=seitengroesse, offset=offset)
        block = seite.get("items") or []
        items.extend(block)
        total = int(seite.get("total") or 0)
        offset += len(block)
        if not block or (total and offset >= total):
            break
    return items


def kandidaten(quelle: dict, items: list[dict]) -> list[dict]:
    """Katalog-Items → Kandidaten im Pipeline-Format (crawler-Kompatibel).

    `wochen` ist unbekannt (None) — der Wochen-Vorfilter lässt None bewusst
    durch. `quelle_kuerzel`/`quelle_id`/`quelle_version` steuern später den
    Trade-Bezug aus dem Quellen-Cache statt über den MQL5-Exporter.
    """
    out = []
    for item in items:
        try:
            signal_id = int(str(item.get("signalId", "")).strip())
        except ValueError:
            continue
        version = str(item.get("version") or "").strip()
        # PelicanTrading liefert das Signalalter (weeks) mit — dann greift der
        # Wochen-Vorfilter erstmals auch für Quellen-Signale; MQL5-Kataloge
        # kennen es nicht (None lässt den Filter bewusst durch).
        wochen = item.get("weeks")
        try:
            wochen = float(wochen) if wochen is not None else None
        except (TypeError, ValueError):
            wochen = None
        out.append({
            "id": signal_id,
            "name": str(item.get("signalName") or str(signal_id)),
            "platform": _PLATTFORM.get(version, ""),
            "url": str(item.get("url")
                       or f"https://www.mql5.com/en/signals/{signal_id}"),
            "abonnenten": item.get("subscribers"),
            "wochen": wochen,
            "quelle_kuerzel": str(quelle.get("kuerzel") or ""),
            "quelle_id": int(quelle["id"]),
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
        except downloader_client.DownloaderError as exc:
            _log(f"Quelle {quelle['kuerzel']}: Katalog nicht erreichbar — {exc}")
            continue
        neu = 0
        for kandidat in kandidaten(quelle, items):
            key = (kandidat["id"], kandidat["platform"])
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
    out.sort(key=lambda s: -float(s.get("abonnenten") or 0))
    return out


def hole_trades(quelle: dict, signal_id: int, version: str, *,
                client: downloader_client.DownloaderClient | None = None) -> tuple[str, bool]:
    """Trades-CSV holen und SHA-gespiegelt cachen. Rückgabe (Pfad, geändert)."""
    cli = client or quellen.client_fuer_quelle(quelle)
    roh = cli.trades_csv(signal_id, version)
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
        except OSError:
            pass  # unlesbar: unten neu schreiben
    pfad = _kuerzel_verzeichnis(quelle) / f"{_version_sicher(version)}_{int(signal_id)}_trades.csv"
    pfad.write_bytes(roh)
    db.store_quellen_artefakt(int(quelle["id"]), signal_id, version,
                              "trades", sha, str(pfad))
    return str(pfad), True


def hole_metrics(quelle: dict, signal_id: int, version: str, *,
                 client: downloader_client.DownloaderClient | None = None) -> dict:
    """Metrics-Antwort holen und cachen; Rückgabe ist das gecachte JSON."""
    cli = client or quellen.client_fuer_quelle(quelle)
    antwort = cli.metrics(signal_id, version)
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
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            pass  # defekter/korrumpierter Cache: neu schreiben (unten)
    pfad = _kuerzel_verzeichnis(quelle) / f"{_version_sicher(version)}_{int(signal_id)}_metrics.json"
    pfad.write_bytes(roh)
    db.store_quellen_artefakt(int(quelle["id"]), signal_id, version,
                              "metrics", sha, str(pfad))
    return antwort


def metrics_zu_stats(antwort: dict | None) -> dict:
    """Metrics-Antwort → Felder der MQL5-Kennzahlenseite (doc/20 §4).

    Nur vorhanden Werte werden gemappt — nichts geraten. `initial_deposit_usd`
    greift automatisch, sobald der Downloader es liefert (bis dahin None und
    die Kapitalbasis-Regel ruht für Quellen-Signale).
    """
    antwort = antwort or {}
    metrics = antwort.get("metrics") if isinstance(antwort.get("metrics"), dict) else {}
    eq_dd = metrics.get("EquityDrawdown")
    if eq_dd is None:
        eq_dd = metrics.get("MaxDDGraphic")
    return {
        "dd_equity_pct": eq_dd,
        "dd_balance_pct": None,
        "monthly_growth_pct": metrics.get("Average3MonthProfit"),
        "subscribers": metrics.get("Subscribers"),
        "initial_deposit_usd": metrics.get("InitialDeposit"),
        # Virtuelle Kapitalbasis (z. B. PelicanMonitor "InitialDepositVirtual"):
        # klar markierte Annahme, KEIN Plattformwert. Dient als Fallback fuer
        # die Forensik (DD-/Schock-Prozente brauchen ein Startkapital), nie
        # als echtes InitialDeposit und nie in den Cent-genauen Abgleich.
        "kapitalbasis_virtual_usd": metrics.get("InitialDepositVirtual"),
        "balance_usd": metrics.get("Balance"),
        # Vom Datenquellen-Monitor aus der VOLLEN Trade-Kurve nachgemessener
        # Max-EQ-DD (TradeEqDrawdownPct) — unabhängige Zweitmessung neben dem
        # gemeldeten Plattform-DD. Geht seit B1 (Intensiv-Review 29./30.09.)
        # als fünftes Maximum in die Drawdown-Schranke.
        # None = Monitor hat keinen Wert (Trades nie/nicht berechenbar geladen).
        "monitor_trade_eq_dd_pct": metrics.get("TradeEqDrawdownPct"),
        # Broker-Kennung des Providers (B6, Intensiv-Review): häufigster
        # ServerCode über die Trades (z. B. PelicanMonitor metrics "Broker").
        # Entcheidet cross_broker=false-Specs (USOIL: 1 vs. 100 Barrel/Lot!).
        "broker_server": metrics.get("Broker"),
        "stats_quelle": "datenquelle_metrics",
    }
