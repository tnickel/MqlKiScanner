# -*- coding: utf-8 -*-
"""EZB-Euro-Referenzkurse: belegte historische Umrechnung nach USD.

Quelle: eurofxref-hist.zip (EZB, taegliche Referenzkurse seit 1999,
EUR-Basis: "1 EUR = X CCY"). Die Datei wird lokal unter data/fx_rates/
gecached und bei Bedarf nachgeladen: Die Historie waechst taeglich, und
frische Trades brauchen frische Kurse — eine alte Datei ist fuer die
Vergangenheit weiterhin korrekt, fuer den aktuellen Rand aber nicht.

Konventionen (gehen als Herkunft in die Befunde ein):
- Kurs zum Handelstag. Fehlt der Tag (Wochenende, TARGET-Feiertag), gilt
  der zuletzt verkuendigte Kurs davor — maximal 10 Kalendertage Ruecklauf,
  darunter bleibt der Wert unbekannt statt still falsch.
- Cross-Kurs in USD: 1 CCY = (EUR/USD) / (EUR/CCY) USD, abgeleitet aus zwei
  EZB-Kursen desselben Verkuendigungstags. EUR selbst liest sich direkt aus
  der USD-Spalte (1 EUR = X USD). Jede Umrechnung ist damit auf belegte
  Kurse mit Datum zurueckfuehrbar.
"""
from __future__ import annotations

import bisect
import csv as _csv
import io
import os
import re
import time
import zipfile
from datetime import date, timedelta

import requests

from . import config

ECB_HISTORY_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip"
CSV_NAME = "eurofxref-hist.csv"
MAX_WALKBACK_DAYS = 10
REFRESH_DAYS = 30
# Wochenend- und Feiertags-Toleranz: Ein fehlender letzter Verkuendigungstag
# bis 4 Tage Rueckstand ist normal (Wochenende, TARGET-Feiertage).
MAX_DATE_LAG_DAYS = 4

_TABLE: dict = {}          # Cache: {(pfad, mtime_ns): {waehrung: (daten, kurse)}}
_DOWNLOAD_TRIED = False    # einmal pro Prozess; kein Retry-Sturm bei Offline


def csv_path() -> "os.PathLike":
    return config.FX_RATES_DIR / CSV_NAME


def _datei_letzter_kurstag(path) -> date | None:
    """Neuester Verkuendigungstag aus den ersten Zeilen der Datei.

    Die EZB-Datei beginnt mit dem NEUESTEN Tag — der aktuelle Rand steht
    also direkt in Zeile 2, ohne die ganze Datei zu parsen. Das Trennzeichen
    ist egal: gezaehlt wird das fuehrende ISO-Datum.
    """
    try:
        with open(path, encoding="utf-8-sig") as fh:
            fh.readline()  # Kopfzeile
            zeile = fh.readline()
        match = re.match(r"\s*(\d{4}-\d{2}-\d{2})", zeile)
        return date.fromisoformat(match.group(1)) if match else None
    except (OSError, ValueError):
        return None


def _parse_csv(text: str) -> dict[str, tuple[list[str], list[float]]]:
    """ECB-CSV -> {waehrung: (aufsteigende Tage, Kurse)}.

    Die offizielle Datei beginnt mit dem NEUESTEN Tag; hier wird je Waehrung
    aufsteigend sortiert, damit ISO-Tage lexikalisch per Bisect suchbar sind.
    """
    reader = _csv.reader(io.StringIO(text))
    header = next(reader, None) or []
    currencies = [h.strip().upper() for h in header[1:]]
    table: dict[str, list[tuple[str, float]]] = {}
    for row in reader:
        if not row or not row[0].strip():
            continue
        day = row[0].strip()
        for cur, cell in zip(currencies, row[1:]):
            if not cur:
                continue
            cell = (cell or "").strip()
            if not cell or cell.upper() == "N/A":
                continue
            try:
                rate = float(cell)
            except ValueError:
                continue
            if rate <= 0:
                continue
            table.setdefault(cur, []).append((day, rate))
    ordered: dict[str, tuple[list[str], list[float]]] = {}
    for cur, pairs in table.items():
        pairs.sort()
        ordered[cur] = ([d for d, _ in pairs], [r for _, r in pairs])
    return ordered


def _load_file(path) -> dict | None:
    try:
        return _parse_csv(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def _refresh(max_age_days: float = REFRESH_DAYS, force: bool = False) -> None:
    """Historie herunterladen, wenn die Datei inhaltlich veraltet ist.

    Veraltet heisst: Der neueste Verkuendigungstag in der Datei liegt mehr
    als MAX_DATE_LAG_DAYS zurueck (Wochenende/Feiertage zugelassen), oder
    die Datei fehlt/ist unlesbar, oder sie ist aelter als max_age_days.
    Scheitert der Download (offline, abgelehnt, defekte Antwort), bleibt es
    still: Eine vorhandene Datei wird weitergenutzt, sonst ohne Kurse
    weitergearbeitet (Exposure bleibt dann ehrlich gesperrt).
    """
    global _DOWNLOAD_TRIED
    if _DOWNLOAD_TRIED and not force:
        return
    path = config.FX_RATES_DIR / CSV_NAME
    letzter_tag = _datei_letzter_kurstag(path) if path.exists() else None
    inhaltlich_veraltet = letzter_tag is None or \
        letzter_tag < date.today() - timedelta(days=MAX_DATE_LAG_DAYS)
    if not force and path.exists() and not inhaltlich_veraltet and \
            (time.time() - path.stat().st_mtime) < max_age_days * 86400:
        return
    _DOWNLOAD_TRIED = True
    try:
        response = requests.get(ECB_HISTORY_URL, timeout=60)
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            member = next(n for n in archive.namelist()
                          if n.lower().endswith(".csv"))
            payload = archive.read(member)
        config.FX_RATES_DIR.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(payload)
        os.replace(temporary, path)
        _TABLE.clear()
    except Exception:
        # Bewusst verschluckt: Kurse sind optional, der Befund meldet es.
        pass


def load() -> dict[str, tuple[list[str], list[float]]]:
    """Kurstabelle (mit Download-Versuch, falls noetig); ohne Datei: leer."""
    _refresh()
    path = config.FX_RATES_DIR / CSV_NAME
    try:
        key = (str(path), path.stat().st_mtime_ns)
    except OSError:
        return {}
    if key not in _TABLE:
        table = _load_file(path) or {}
        _TABLE.clear()
        _TABLE[key] = table
    return _TABLE[key]


def status() -> dict:
    """Diagnose fuer Befund-Texte: geladen? bis zu welchem Tag?"""
    table = load()
    if not table:
        return {"geladen": False, "quelle": ECB_HISTORY_URL,
                "ordner": str(config.FX_RATES_DIR)}
    usd_dates = table.get("USD", ([], []))[0]
    return {"geladen": True, "quelle": ECB_HISTORY_URL,
            "ordner": str(config.FX_RATES_DIR),
            "letzte_kursdatum": usd_dates[-1] if usd_dates else None,
            "waehrungen": sorted(table)}


def can_convert(currency: str) -> bool:
    """Ist fuer diese Waehrung ueberhaupt eine Umrechnung belegbar?

    Ohne Kursdatei: nur USD. EUR ist die Basewaehrung der EZB-Datei (keine
    eigene Spalte) und wird direkt aus der USD-Spalte gelesen.
    """
    currency = (currency or "").upper()
    if currency == "USD":
        return True
    table = load()
    if not table.get("USD"):
        return False
    return currency == "EUR" or currency in table


def usd_per(currency: str, when: date) -> dict | None:
    """Wie viel USD ist 1 Einheit `currency` am Handelstag `when` wert?

    Rueckgabe {"rate": faktor, "date": verkuendigungstag} oder None
    (Waehrung unbekannt, kein Kurs im 10-Tage-Fenster, vor 1999).
    """
    currency = (currency or "").upper()
    if not currency:
        return None
    table = load()
    usd_series = table.get("USD")
    if not usd_series:
        return None
    if currency == "USD":
        return {"rate": 1.0, "date": when.isoformat()}
    # EUR ist die Basis der EZB-Datei: "1 EUR = X USD" steht in der USD-Spalte.
    series = usd_series if currency == "EUR" else table.get(currency)
    if not series:
        return None
    target = when.isoformat()
    idx = bisect.bisect_right(series[0], target) - 1
    if idx < 0:
        return None
    rate_date, ccy_per_eur = series[0][idx], series[1][idx]
    if (when - date.fromisoformat(rate_date)).days > MAX_WALKBACK_DAYS:
        return None
    if currency == "EUR":
        return {"rate": ccy_per_eur, "date": rate_date}
    usd_idx = bisect.bisect_right(usd_series[0], rate_date) - 1
    if usd_idx < 0 or usd_series[0][usd_idx] != rate_date:
        return None
    return {"rate": usd_series[1][usd_idx] / ccy_per_eur, "date": rate_date}
