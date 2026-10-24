"""One read-only capital decision for closing, exposure and equity analyses.

``kapital`` is the first-trade anchor BEFORE separate account costs.
``injektion_usd`` supplements the already present pre-start balance rows, so
``sum(prestart balances) + injektion_usd == kapital``. Later flows and all costs
remain in the caller's original accounting. Model sizing lives exclusively in
``abonnenten_modellkapital``; this module supplies precedence and provenance.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from . import abonnenten_modellkapital as schaetzer
from . import config
from .zahlen import ist_endliche_zahl as _number

VERSION = 1
_CACHE = {}
_MODEL_SOURCES = {
    "komplex_lot_pnl_regression": "modell_lot_pnl",
    "grobe_lot_kalibrierung": "modell_lots_kalibriert",
    "fallback_10000": "modell_fallback_10000",
    "komplex_closing_dd_anker": "modell_closing_dd_anker",
}
_DESCRIPTIONS = {
    "csv_einzahlungen": "CSV-Ein-/Auszahlungen vor Handelsbeginn",
    "signalseite_initial_deposit": "Belegtes Quellen-Anfangskapital plus vorhandene Vorstartbuchungen",
    "manuell": "Explizit angegebenes Anfangskapital plus vorhandene Vorstartbuchungen",
    "extern": "Explizit extern angegebenes Anfangskapital plus vorhandene Vorstartbuchungen",
    "web": "Anfangskapital von der Quellenseite plus vorhandene Vorstartbuchungen",
    "modell_lot_pnl": "Modellkapital aus stabiler Lot-/PnL-Regression; keine belegte Kontogroesse",
    "modell_lots_kalibriert": "Grobe Lotschaetzung aus belegten Referenzprofilen; keine belegte Kontogroesse",
    "modell_fallback_10000": "Modellannahme 10.000 USD mangels tragfaehigerer Kapitalbasis",
    "modell_closing_dd_anker": "Modellkapital aus unabhaengigem Closing-DD-Anker; keine belegte Kontogroesse",
}


def _audit_value(value):
    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)  # JSON has no NaN/Infinity; preserve their diagnosis.
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return repr(value)


def ist_modellquelle(value):
    """Recognise current models and historical virtual assumptions for gates."""
    if isinstance(value, dict):
        if (value.get("modell") is True or value.get("kapitalbasis_modell") is True
                or value.get("basis_typ") == "modell"):
            return True
        return any(ist_modellquelle(value.get(key)) for key in (
            "quelle", "herkunft", "methode", "startkapital_quelle", "kapitalbasis_verwendet_quelle"))
    source = str(value or "").strip().lower()
    return source.startswith(("modell_", "virtuell", "virtuell_", "komplex_", "grobe_lot_", "fallback_10000"))


def beschreibung(value):
    """A short label; callers can display the complete decision separately."""
    if isinstance(value, dict):
        source = value.get("quelle") or value.get("herkunft") or value.get("methode") or value.get("startkapital_quelle")
    else:
        source = value
    source = str(source or "").strip().lower()
    source = _MODEL_SOURCES.get(source, source)
    if source in ("manuell_eingabe", "manuell_angegeben"):
        source = "manuell"
    if source in _DESCRIPTIONS:
        label = _DESCRIPTIONS[source]
        if ist_modellquelle(value) and not ist_modellquelle(source):
            label += " (als Modellannahme gekennzeichnet)"
        return label
    if ist_modellquelle(value):
        return "Historische virtuelle Kapitalannahme; keine belegte Kontogroesse"
    return source or "Kapitalherkunft unbekannt"


def kalibrierung_sha256(pool):
    """Canonical digest compatible with frozen subscriber calibration pools."""
    raw = json.dumps(pool, ensure_ascii=False, sort_keys=True, allow_nan=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _validate_calibration(pool):
    if (not isinstance(pool, dict) or type(pool.get("version")) is not int
            or pool["version"] != schaetzer.VERSION
            or pool.get("basis") != "ausschliesslich_belegte_usd_startkapitalien"
            or type(pool.get("referenzen_n")) is not int or pool["referenzen_n"] < 0
            or not isinstance(pool.get("gruppen"), list)):
        raise ValueError("Ungueltiges Kalibrierungsschema")
    # Reject non-JSON/nonfinite values rather than repairing a signed snapshot.
    json.dumps(pool, ensure_ascii=False, allow_nan=False)
    identities, group_keys, count = set(), set(), 0
    for group in pool["gruppen"]:
        if not isinstance(group, dict):
            raise ValueError("Ungueltige Kalibrierungsgruppe")
        key, rows = group.get("kontraktgruppe"), group.get("referenzen")
        if (not isinstance(key, list) or len(key) != 3
                or not all(isinstance(value, str) and value.strip() for value in key[:2])
                or not _number(key[2]) or key[2] <= 0
                or not isinstance(rows, list) or type(group.get("n")) is not int
                or group["n"] != len(rows) or tuple(key) in group_keys):
            raise ValueError("Ungueltige Kontrakt-/Referenzgruppe")
        group_keys.add(tuple(key))
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("Ungueltige Kapitalreferenz")
            ident = row.get("quellen_uid"), row.get("id")
            if (not all(isinstance(value, str) and value for value in ident)
                    or ident in identities
                    or any(not _number(row.get(field)) or row[field] <= 0
                           for field in ("kapital_usd", "median_lot", "usd_je_lot"))
                    or not math.isclose(row["kapital_usd"] / row["median_lot"], row["usd_je_lot"], rel_tol=1e-9)):
                raise ValueError("Ungueltiger oder doppelter USD-Kapitalbeleg")
            identities.add(ident)
            count += 1
    if count != pool["referenzen_n"]:
        raise ValueError("Referenzzahl passt nicht zum Kalibrierungssnapshot")
    return pool


def lade_kalibrierung_mit_beleg(path=None):
    """Read a hash-checked explicit snapshot, never a database or network.

    Accepts ``{kalibrierung: pool, sha256: canonical_pool_sha}`` or a raw pool
    with adjacent ``kalibrierung.sha256``. Missing or invalid files return None
    plus a diagnostic. Cached values are copied before returning.
    """
    target = Path(path) if path is not None else Path(config.DATA_DIR) / "kapitalbasis" / "kalibrierung.json"
    proof = {"pfad": str(target), "status": "fehlt"}
    try:
        stat = target.stat()
        sidecar = target.with_suffix(".sha256")
        try:
            side_stat = sidecar.stat()
            side_key = side_stat.st_mtime_ns, side_stat.st_size
        except FileNotFoundError:
            side_key = None
        key = str(target.resolve()), stat.st_mtime_ns, stat.st_size, side_key
        if key in _CACHE:
            return deepcopy(_CACHE[key])
        raw = target.read_bytes()
        document = json.loads(raw.decode("utf-8-sig"))
        if isinstance(document, dict) and "kalibrierung" in document:
            pool, expected = document["kalibrierung"], document.get("sha256")
            proof["hashquelle"] = "snapshot_envelope"
        else:
            pool = document
            expected = sidecar.read_text(encoding="utf-8-sig").strip().split()[0] if side_key is not None else None
            proof["hashquelle"] = "sha256_sidecar"
        _validate_calibration(pool)
        digest = kalibrierung_sha256(pool)
        if not isinstance(expected, str) or expected.strip().lower() != digest:
            raise ValueError("Kalibrierungs-SHA fehlt oder stimmt nicht mit dem Inhalt ueberein")
        proof.update(status="geprueft", sha256=digest, referenzen_n=pool["referenzen_n"],
                     datei_sha256=hashlib.sha256(raw).hexdigest())
        result = deepcopy(pool), proof
        # Keep a small process-local cache; changing file metadata invalidates it.
        if len(_CACHE) >= 8:
            _CACHE.clear()
        _CACHE[key] = deepcopy(result)
        return result
    except FileNotFoundError:
        proof["grund"] = "Kein expliziter gemeinsamer Kalibrierungssnapshot vorhanden"
    except (OSError, ValueError, TypeError, IndexError, KeyError) as exc:
        proof.update(status="fehler", grund=str(exc))
    return None, proof


def lade_kalibrierung(path=None):
    """Return the verified pool or None; no implicit creation or repair."""
    return lade_kalibrierung_mit_beleg(path)[0]


def _currency_claims(context, stats):
    claims = {}
    for owner, values in (("kontext", context), ("stats", stats),
                          ("kontext.quellen_stats", context.get("quellen_stats") or {})):
        for field in ("account_currency", "trade_money_currency", "native_account_currency"):
            raw = values.get(field)
            if raw is not None and str(raw).strip():
                claims[f"{owner}.{field}"] = str(raw).strip().upper()
    return claims


def _prestart(parsed):
    trades = getattr(parsed, "trades", []) if parsed is not None else []
    first = min(trade.open_time for trade in trades) if trades else None
    flows = [flow for flow in getattr(parsed, "balances", []) if first is not None and flow.time <= first]
    costs = [cost for cost in getattr(parsed, "costs", []) if first is not None and cost.time < first]
    if any(not _number(flow.amount) for flow in [*flows, *costs]):
        raise ValueError("Nichtendliche Vorstartbuchung im Trade-Export")
    return first, flows, math.fsum(flow.amount for flow in flows), math.fsum(cost.amount for cost in costs)


def _decision(capital, injection, source, proof, *, estimate=None, method=None, reason=None):
    model = ist_modellquelle(source)
    assumptions = ["Vorhandene exportierte Ein-/Auszahlungen bleiben in der Berechnung erhalten",
                   "Separate Kontokosten werden einmal aus dem Kapitalanker vor Kosten gebucht"]
    if model:
        assumptions.insert(0, "Hypothetisches USD-Modellkapital; keine belegte reale Kontogroesse")
    if estimate is not None:
        # The subscriber estimator also serves a separate no-flow scenario.
        # Its sizing diagnostics remain intact; this caller retains cashflows.
        estimate = deepcopy(estimate)
        estimate["annahmen"] = [line for line in estimate.get("annahmen", [])
                                if line != "Keine Ein-/Auszahlungen innerhalb des modellierten Tradefensters"]
        estimate["annahmen"].append(assumptions[1] if model else assumptions[0])
    return {"version": VERSION, "kapital": float(capital), "waehrung": "USD",
            "injektion_usd": float(injection), "quelle": source, "modell": model,
            "basis_typ": "modell" if model else "belegt", "gueltig": capital > 0,
            "grund": reason or ("Positive Kapitalbasis vor separaten Vorstartkosten" if capital > 0
                                else "Bekannte CSV-Nettoanfangsbasis ist nicht positiv; kein Modellkapital eingesetzt"),
            "methode": method or source, "beschreibung": beschreibung(source),
            "annahmen": assumptions,
            "unsicherheit": (estimate or {}).get("unsicherheit") if model else None,
            "beleg": proof, "schaetzung": estimate}


def aufloesen(parsed, *, stats=None, kapitalbasis_usd=None, kapitalbasis_quelle=None,
              broker=None, kontext=None, calibration=None):
    """Resolve the shared USD capital anchor without changing input or storage.

    Recorded positive pre-start deposits take precedence over external inputs.
    A known nonpositive CSV net anchor stays nonpositive. Source initial capital
    or an explicit manual amount is next, followed by the single shared model.
    An explicit foreign/conflicting currency raises ValueError. In the absence
    of currency claims the historic generic-engine USD-input contract applies;
    this is recorded as an input assumption, not native currency evidence.
    """
    context = deepcopy(kontext) if isinstance(kontext, dict) else {}
    stats = deepcopy(stats) if isinstance(stats, dict) else {}
    claims = _currency_claims(context, stats)
    currencies = set(claims.values())
    if len(currencies) > 1:
        raise ValueError("Widerspruechliche Kontowaehrung/Trade-Betragswaehrung; keine USD-Kapitalberechnung moeglich")
    if currencies and currencies != {"USD"}:
        raise ValueError("Kapitalberechnung erfordert USD-Tradebetraege; explizite Fremdwaehrung wird nicht umetikettiert")
    first, flows, before, costs = _prestart(parsed)
    proof = {"signal_ref": context.get("signal_ref"), "trades_sha256": context.get("trades_sha256"),
             "waehrungsangaben": claims,
             "usd_basis": "explizite_uebereinstimmende_waehrungsangaben" if claims else "generischer_usd_inputvertrag_ohne_nativen_waehrungsbeleg",
             "erster_trade": first.isoformat() if first else None,
             "vorstart_flows_usd": before, "vorstart_flows_n": len(flows),
             "positive_vorstart_einzahlungen_n": sum(flow.amount > 0 for flow in flows),
             "spaetere_flows_n": sum(flow.time > first for flow in getattr(parsed, "balances", [])) if first else 0,
             "vorstart_kosten_usd": costs, "kosten_im_kapitalanker_enthalten": False,
             "spaetere_flows_bleiben_erhalten": True}
    if any(flow.amount > 0 for flow in flows):
        return _decision(before, 0.0, "csv_einzahlungen", proof)

    ignored = []
    source = str(kapitalbasis_quelle or "").strip().lower()
    if kapitalbasis_usd is not None and ist_modellquelle(source):
        ignored.append({"feld": "kapitalbasis_usd", "quelle": source,
                        "originalwert": _audit_value(kapitalbasis_usd),
                        "grund": "Historischer virtueller Fixwert ersetzt die aktuelle Schaetzmethodik nicht"})
        kapitalbasis_usd = None
    if kapitalbasis_usd is not None:
        from_source = source in ("signalseite_initial_deposit", "native_initial_deposit_usd")
        if not _number(kapitalbasis_usd) or kapitalbasis_usd <= 0:
            if not from_source:
                raise ValueError("Explizites manuelles Anfangskapital muss positiv und endlich sein")
            ignored.append({"feld": "kapitalbasis_usd", "quelle": source,
                            "originalwert": _audit_value(kapitalbasis_usd),
                            "grund": "Kein positiver endlicher Quellen-Anfangskapitalbeleg"})
        else:
            proof.update(externer_anker_usd=float(kapitalbasis_usd), eingabe_quelle=kapitalbasis_quelle,
                         ignorierte_angaben=ignored)
            return _decision(before + kapitalbasis_usd, kapitalbasis_usd,
                             str(kapitalbasis_quelle).strip() if kapitalbasis_quelle else "signalseite_initial_deposit", proof)

    # Native metadata may accompany generic callers without a separate amount.
    merged_stats = deepcopy(context.get("quellen_stats") or {})
    merged_stats.update(stats)
    initial = merged_stats.get("initial_deposit_usd")
    if _number(initial) and initial > 0:
        proof.update(externer_anker_usd=float(initial), eingabe_quelle="stats.initial_deposit_usd",
                     ignorierte_angaben=ignored)
        return _decision(before + initial, initial, "signalseite_initial_deposit", proof)
    if initial is not None:
        ignored.append({"feld": "stats.initial_deposit_usd", "originalwert": _audit_value(initial),
                        "grund": "Kein positiver endlicher Quellen-Anfangskapitalbeleg"})
    if merged_stats.get("kapitalbasis_virtual_usd") is not None:
        ignored.append({"feld": "stats.kapitalbasis_virtual_usd",
                        "originalwert": _audit_value(merged_stats["kapitalbasis_virtual_usd"]),
                        "grund": "Historischer virtueller Fixwert ist kein belegtes Anfangskapital"})
    proof["ignorierte_angaben"] = ignored
    if calibration is None:
        pool, calibration_proof = lade_kalibrierung_mit_beleg()
    else:
        try:
            pool = deepcopy(_validate_calibration(calibration))
            calibration_proof = {"status": "explizit_geprueft", "sha256": kalibrierung_sha256(pool),
                                 "referenzen_n": pool["referenzen_n"], "quelle": "expliziter_parameter"}
        except (ValueError, TypeError, KeyError) as exc:
            pool, calibration_proof = None, {"status": "fehler", "quelle": "expliziter_parameter", "grund": str(exc)}
    proof["kalibrierung"] = calibration_proof
    subject = context
    subject["quellen_stats"] = merged_stats
    subject.setdefault("account_currency", "USD")
    # Empty original claims also mean generic USD input, explicitly documented
    # above. Normalise that contract for the existing single estimator API.
    if not str(subject.get("account_currency") or "").strip():
        subject["account_currency"] = "USD"
    if broker:
        subject["broker_server"] = broker
    estimate = schaetzer.schaetze_kapital(subject, parsed, pool)
    capital = estimate["kapital"]
    if not _number(capital):
        raise ValueError("Kapitalschaetzer lieferte keinen endlichen Anker")
    if estimate.get("modell") is True:
        source = _MODEL_SOURCES.get(estimate.get("methode"))
        if source is None:
            raise ValueError("Unbekannte Modellkapital-Methode")
    else:
        # A prior, correctly bound initial-deposit forensic proof may be the
        # remaining known anchor. Its estimator value already includes flows.
        source = "signalseite_initial_deposit"
    return _decision(capital, capital - before, source, proof, estimate=estimate,
                     method=estimate.get("methode"))
