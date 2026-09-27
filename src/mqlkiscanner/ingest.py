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

_PLATTFORM = {"mql4": "mt4", "mql5": "mt5"}
_KUERZEL_SICHER = re.compile(r"[^A-Za-z0-9_\-]")


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
        out.append({
            "id": signal_id,
            "name": str(item.get("signalName") or str(signal_id)),
            "platform": _PLATTFORM.get(version, ""),
            "url": str(item.get("url")
                       or f"https://www.mql5.com/en/signals/{signal_id}"),
            "abonnenten": item.get("subscribers"),
            "wochen": None,
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
        return str(alt["path"]), False
    pfad = _kuerzel_verzeichnis(quelle) / f"{version}_{signal_id}_trades.csv"
    pfad.write_bytes(roh)
    db.store_quellen_artefakt(int(quelle["id"]), signal_id, version,
                              "trades", sha, str(pfad))
    return str(pfad), True


def hole_metrics(quelle: dict, signal_id: int, version: str, *,
                 client: downloader_client.DownloaderClient | None = None) -> dict:
    """Metrics-Antwort holen und cachen; Rückgabe ist das gecachte JSON."""
    cli = client or quellen.client_fuer_quelle(quelle)
    antwort = cli.metrics(signal_id, version)
    roh = json.dumps(antwort, ensure_ascii=False, sort_keys=True,
                     default=str).encode("utf-8")
    sha = hashlib.sha256(roh).hexdigest()
    alt = db.get_quellen_artefakt(int(quelle["id"]), signal_id, version, "metrics")
    if alt and alt.get("sha256") == sha and alt.get("path") \
            and Path(alt["path"]).exists():
        try:
            return json.loads(Path(alt["path"]).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass  # defekter Cache: neu schreiben (unten)
    pfad = _kuerzel_verzeichnis(quelle) / f"{version}_{signal_id}_metrics.json"
    pfad.write_text(json.dumps(antwort, ensure_ascii=False, indent=1, default=str),
                    encoding="utf-8")
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
        "balance_usd": metrics.get("Balance"),
        "stats_quelle": "datenquelle_metrics",
    }
