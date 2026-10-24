"""Explicit, local-only capital scenarios for the subscriber data workflow."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import config, db, parser
from .abonnenten_analyse_store import now


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    allow_nan=False, default=str).encode("utf-8")).hexdigest()


def _file_state(path):
    path = Path(path)
    try:
        stat = path.stat()
        return {"path": str(path.resolve()), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    except OSError:
        return {"path": str(path.resolve()), "missing": True}


def berechne_bestand(store, run, entries, log, stopped):
    """Publish only nested model fields; keep original facts and exports intact."""
    from .abonnenten_analyse import Angehalten, CAPITAL_MODEL_VERSION
    from .abonnenten_modellkapital import kalibriere, schaetze_kapital
    from .abonnenten_modellrechnung import berechne_modell
    from .kapitalbasis import lade_kalibrierung_mit_beleg

    def check_stop():
        if stopped():
            raise Angehalten("Modellberechnung angehalten")

    parsed_by_ref, parse_errors = {}, {}
    log("Gespeicherte Trade-Exporte und Identitäten für das Kapitalmodell prüfen …")
    for entry in entries:
        check_stop()
        ref = entry["signal_ref"]
        path, sha = entry.get("trades_path"), entry.get("trades_sha256")
        if not path or not sha:
            parse_errors[ref] = "Kein gespeicherter Trade-Export mit SHA-Beleg vorhanden."
            continue
        try:
            db.verify_trade_file(path, sha)
            parsed = parser.load_export(path)
            if not parsed.trades:
                raise ValueError("Keine abgeschlossenen Trades im gespeicherten Export.")
            if entry.get("trades") is not None and entry["trades"] != len(parsed.trades):
                raise ValueError("Gespeicherte Trade-Anzahl passt nicht zum unveränderten Export.")
            parsed_by_ref[ref] = parsed
        except (OSError, ValueError, TypeError, KeyError) as exc:
            parse_errors[ref] = f"{type(exc).__name__}: {exc}"

    check_stop()
    calibration = run.get("modell_kalibrierung")
    calibration_receipt = {"quelle": "eingefrorene Auftragskalibrierung"}
    if not isinstance(calibration, dict) or _digest(calibration) != run.get("modell_kalibrierung_sha256"):
        calibration, calibration_receipt = lade_kalibrierung_mit_beleg()
        # A missing shared reference pool must not silently create a different
        # lot/capital scale just for this page. The explicit 10k stage applies.
        if calibration is None:
            calibration = kalibriere([])
    calibration_sha = _digest(calibration)
    settings = config.load_settings()
    inputs = {"version": CAPITAL_MODEL_VERSION, "calibration_sha": calibration_sha,
              "calibration_receipt": calibration_receipt,
              "price_settings": {key: settings.get(key) for key in ("markt_symbol_suffix", "symbol_aliases")},
              "implementation": [_file_state(path) for path in (
                  Path(__file__), Path(__file__).with_name("abonnenten_modellkapital.py"),
                  Path(__file__).with_name("kapitalbasis.py"),
                  Path(__file__).with_name("abonnenten_modellrechnung.py"),
                  Path(__file__).parent / "forensics" / "equity_rekonstruktion.py")],
              "contracts": _file_state(config.CONTRACT_SPECS_FILE),
              "h1_cache": _file_state(config.DATA_DIR / "kursdaten.db"),
              "h1_wal": _file_state(config.DATA_DIR / "kursdaten.db-wal"),
              "fx_files": [_file_state(path) for path in sorted(config.FX_RATES_DIR.glob("*.csv"))]}
    store.update(run["id"], modell_kalibrierung=calibration,
                 modell_kalibrierung_sha256=calibration_sha, modell_inputbasis=inputs,
                 modell_annahme="Keine Ein- oder Auszahlungen; vorhandene Kapitalbewegungen werden nur im Modell ignoriert.",
                 modell_exporte_geprueft=len(parsed_by_ref), modell_abgeschlossen=False,
                 modell_bearbeitet=0)
    for index, entry in enumerate(entries, 1):
        check_stop()
        ref = entry["signal_ref"]
        parsed = parsed_by_ref.get(ref)
        capital = schaetze_kapital(entry, parsed, calibration=calibration)
        basis = _digest({"inputs": inputs, "capital": capital, "ref": ref,
                         "quellen_uid": entry.get("quellen_uid"), "id": entry.get("id"),
                         "trade_sha": entry.get("trades_sha256"),
                         "trade_count": entry.get("trades"),
                         "source_context": {key: entry.get(key) for key in
                             ("quelle", "quelle_version", "account_currency", "trade_money_currency")},
                         "source_stats": entry.get("quellen_stats"),
                         "prior_terminal": (entry.get("equity") or {}).get("kursdaten_terminal"),
                         "complete": entry.get("trade_history_complete"),
                         "error": parse_errors.get(ref)})
        old = entry.get("modell") or {}
        if old.get("berechnungsbasis") == basis and old.get("berechnet_am"):
            continue
        log(f"Kapitalmodell {index}/{len(entries)}: {entry.get('quelle')} · {entry.get('name')}")
        result = berechne_modell(entry, capital)
        # Parser/receipt conflicts are never repaired by assuming capital.
        if ref in parse_errors:
            result.update(status="datenluecke", grund=parse_errors[ref],
                          equity_dd_pct=None, equity_dd_usd=None, retdd_jahr=None,
                          closing_dd_pct=None, closing_dd_usd=None, nettogewinn_usd=None,
                          rendite_zeitraum_pct=None, cagr_jahr_pct=None)
        result.update(version=CAPITAL_MODEL_VERSION, berechnungsbasis=basis,
                      kalibrierung_sha256=calibration_sha, berechnet_am=now())
        entry["modell"] = result
        store.save_task(run["id"], entry)
        store.update(run["id"], modell_bearbeitet=index)
        check_stop()
    store.update(run["id"], modell_bearbeitet=len(entries), modell_abgeschlossen=True)
    return entries
