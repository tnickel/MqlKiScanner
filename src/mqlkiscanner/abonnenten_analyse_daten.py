"""Aktuelle, belegte Daten für den getrennten Abonnenten-Recherchelauf.

Schreibt ausschließlich normale Quellenartefakte und Trade-Snapshots. Die
Ergebnisse gehen an den eigenen Auftragsstore des Aufrufers; Hauptworkflow,
Ampeln und unabhängige Studien werden hier niemals gespeichert. Der Aufrufer
hält während des gesamten Kontextes das gemeinsame Scan-/Studienlauf-Lock.
"""
from __future__ import annotations

import datetime as dt
import math
from collections.abc import Mapping

from . import config, db, engine, ingest, kursdaten, parser, portfolio_statistik, quellen
from .forensics import exposure
from .pipeline import _kapitalbasis_abgleich
from .signal_identity import identity_key
from .studien_batch import _rekonstruiere_mit_feed_fallback

POLICY_VERSION = "abonnenten_recherche_v1"
MIN_MONATE = 2.0
MIN_TRADES = 50
MESSHINWEIS = (
    "Historisches Exportfenster; aktuelle offene Positionen nicht erfasst. "
    "Floating der exportierten Positionen aus H1-Bar-Schlüssen; keine "
    "Intrabar-Tiefs und kein exakter aktueller Broker-Maximaldrawdown. "
    "Jahres-RetDD ist annualisiert aus der ausgewiesenen Trade-Zeitspanne; "
    "zwei Monate und 50 Trades garantieren keine statistische Belastbarkeit."
)


def _zahl(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _validiere_metrics(raw: dict, sid: int, version: str) -> dict:
    if not isinstance(raw, dict) or not isinstance(raw.get("metrics"), dict):
        raise ValueError("Kennzahlenantwort ist kein belegtes Quellenobjekt.")
    for key in ("providerId", "signalId", "id"):
        if key in raw and str(raw[key]) != str(sid):
            raise ValueError("Kennzahlen gehören zu einer anderen Anbieter-ID.")
    if raw.get("version") is not None and str(raw["version"]).strip().lower() != version:
        raise ValueError("Kennzahlen gehören zu einer anderen Quellen-/Plattformversion.")
    return raw["metrics"]


def robo_quellenwerte(raw: dict, sid: int, version: str) -> dict:
    """Explizite Ratingwerte lesen; keine Annahme über native Trades/Lots.

    Ein GET belegt den Lesezeitpunkt am Client, nicht den Zeitpunkt der letzten
    Plattformmessung dieser Finanzwerte. ProfitUsd ist ausdrücklich USD;
    YieldWindowPct wird unverändert mit seinem eigenen Zeitraum ausgewiesen.
    """
    metrics = _validiere_metrics(raw, sid, version)
    profit = _zahl(metrics.get("ProfitUsd"))
    yield_pct = _zahl(metrics.get("YieldWindowPct"))
    months = _zahl(metrics.get("YieldWindowMonths"))
    if months is not None and (months < 0 or not months.is_integer()):
        months = None
    complete = profit is not None or (yield_pct is not None and months is not None)
    state = ("unbekannt" if profit is None else "positiv" if profit > 0
             else "negativ" if profit < 0 else "unveraendert")
    return {
        "auswertung_typ": "quellenprofitabilitaet", "gewinn_usd": profit,
        "rendite_quelle_pct": yield_pct, "rendite_quelle_monate": months,
        "rating_balance_usd": _zahl(metrics.get("RatingBalanceUsd")),
        "profitabilitaet": state, "rating_currency": "USD",
        "daten_gelesen_am": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "finanzdaten_stand": None, "data_complete": complete, "eligible": False,
        "trades": None,
        "retdd_jahr": None, "retdd_zeitraum": None, "equity_dd_pct": None,
        "grund": ("Quellengewinn/Rendite verfügbar; RetDD ohne belastbaren offenen Equity-DD nicht bestimmbar."
                  if complete else "Keine auswertbaren Gewinn-/Renditeangaben in den Quellenkennzahlen."),
        "messhinweis": "Gewinn in USD und Rendite sind Quellenangaben, nicht aus Einzeltrades nachgerechnet. "
                       "Datum der Finanzwerte unbekannt; Lesezeitpunkt ist keine neue Plattformmessung. "
                       "Offener Equity-DD und RetDD bleiben unbestimmt. "
                       "Eine ausreichende Trade-Historie ist damit nicht nachgewiesen.",
        "quellen_profitabilitaet": {key: metrics.get(key) for key in (
            "ProfitUsd", "YieldWindowPct", "YieldWindowMonths", "RatingBalanceUsd", "RatingCurrency")},
    }


def pruefe_mindestmaterial(dauer_monate, trades) -> tuple[bool, str]:
    """Reine Prüfung des expliziten 2-Monate-/50-Positionen-Profils."""
    monate, anzahl = _zahl(dauer_monate), _zahl(trades)
    if monate is None or monate < MIN_MONATE:
        return False, "Trade-Historie unter 2 Monaten oder Zeitspanne unbelegt."
    if anzahl is None or not anzahl.is_integer() or anzahl < MIN_TRADES:
        return False, "Weniger als 50 abgeschlossene normalisierte Trades."
    return True, ""


def pruefe_kriterien(daten: dict) -> tuple[bool, str]:
    """Keine Hauptworkflow-Ampel, 3-Monats-, DD- oder Score-Sperre übernehmen.

    Mess-/Währungs-/Kapitalbelege prüft der Datenservice vor diesem Schritt.
    Eine zusätzlich gewählte DD-Grenze prüft anschließend der Koordinator.
    """
    if daten.get("hard_excluded"):
        return False, daten.get("ausschlussgrund") or "Bestätigter harter Ausschlussbefund."
    ok, grund = pruefe_mindestmaterial(daten.get("dauer_monate"), daten.get("trades"))
    if not ok:
        return ok, grund
    dd = _zahl(daten.get("equity_dd_pct"))
    if dd is None or dd <= 0:
        return False, "Kein positiver belastbarer gemessener Floating-Equity-DD als RetDD-Nenner."
    retdd = _zahl(daten.get("retdd_jahr"))
    if retdd is None or retdd <= 0:
        return False, "Jahres-RetDD unbelegt oder nicht positiv."
    return True, "Recherchekandidat; keine neue grüne Handelsfreigabe."


def equity_nenner(report: dict, trades: int) -> tuple[float | None, str]:
    """Nur vollständige Floating-Messungen; freigegebene Teilstudien reichen nicht."""
    if (report.get("verlaesslich") is not True or report.get("status") != "ok"
            or report.get("teilmessung") or report.get("fx_luecke")
            or report.get("symbole_nicht_betrachtet") or report.get("symbole_ohne_kurse")
            or report.get("symbole_ohne_kontrakt")):
        return None, ("Floating-Equity-Messung nicht vollständig belastbar: "
                      + str(report.get("grund") or report.get("status") or "fehlende Messbelege"))
    if (report.get("trades_total") != trades
            or report.get("trades_mit_kurs_und_kontrakt") != trades):
        return None, "Nicht alle abgeschlossenen Trades sind durch Kurse und Kontrakte abgedeckt."
    dd = _zahl(report.get("equity_dd_pct_raw"))
    if dd is None or dd <= 0:
        return None, "Ungerundeter positiver maximaler relativer Floating-Equity-DD fehlt."
    return dd, ""


def _json_sicher(value):
    """Keine NaN/Inf, Datetime- oder NumPy-Objekte im persistenten Ergebnis."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_sicher(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_sicher(item) for item in value]
    if hasattr(value, "tolist"):
        return _json_sicher(value.tolist())
    if hasattr(value, "item"):
        return _json_sicher(value.item())
    return str(value)


class _Abbruch(RuntimeError):
    pass


class AnalyseDaten:
    """Ein Kursanbieter pro Batch, lazy verbunden und am Kontextende bereinigt."""

    def __init__(self, settings: dict, log=None):
        self.settings = dict(settings)
        self.log = log or (lambda _text: None)
        self.anbieter = None
        self._geschlossen = False

    def __enter__(self):
        if self._geschlossen:
            raise RuntimeError("Geschlossener Analysekontext kann nicht wiederverwendet werden.")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._geschlossen = True
        if self.anbieter is not None:
            try:
                self.anbieter.beenden()
            except Exception as error:
                self.log(f"Kursdaten-Cleanup fehlgeschlagen: {type(error).__name__}: {error}")
                if exc_type is None:
                    raise
        return False

    @staticmethod
    def _stop(should_stop):
        if should_stop():
            raise _Abbruch("Abbruch angefordert; fertige Daten bleiben erhalten.")

    def _kurse(self):
        if self.anbieter is None:
            self.anbieter = kursdaten.KursDaten(self.settings)
        if getattr(self.anbieter, "terminal_idx", 0) != 0:
            ok, grund = self.anbieter.zurueck_zum_ersten_terminal()
            if not ok:
                raise ValueError(f"Referenzterminal konnte nicht zurückgesetzt werden: {grund}")
        ok, grund = self.anbieter.starten()
        if not ok:
            raise ValueError(f"Kursdaten nicht verfügbar: {grund}")
        return self.anbieter

    def berechne(self, entry: dict, should_stop=lambda: False) -> dict:
        """Gezielt aktualisieren, volle Forensik rechnen und neue Policy anwenden.

        Ein Quellenfehler wird als einzelner nicht berechenbarer Anbieter
        zurückgegeben. Kein Offline-/10k-Fallback und keine Haupt-DB-Bewertung.
        """
        result = {
            "trades_path": "", "trades_sha256": "", "forensik": {}, "equity": {},
            "eligible": False, "data_complete": False, "grund": "", "retdd_jahr": None, "retdd_zeitraum": None,
            "equity_dd_pct": None, "ertrag_monat_geom_pct": None, "cagr_jahr_pct": None,
            "dauer_monate": None, "trades": 0, "kapitalbasis_usd": None,
            "account_currency": None, "messhinweis": MESSHINWEIS, "hard_excluded": False,
            "policy_version": POLICY_VERSION,
        }
        try:
            if self._geschlossen:
                raise ValueError("Analysekontext ist bereits geschlossen.")
            self._stop(should_stop)
            quelle = db.get_quelle(int(entry["quelle_id"]))
            if not quelle or not quelle.get("aktiv"):
                raise ValueError("Die ausgewählte Datenquelle fehlt oder ist inaktiv.")
            source, sid = identity_key(entry)
            if (db.kanonische_quelle(quelle["kuerzel"]) != source
                    or not entry.get("quellen_uid")
                    or str(quelle.get("quellen_uid") or "") != str(entry["quellen_uid"])):
                raise ValueError("Quellenidentität passt nicht zum eingefrorenen Prüfauftrag.")
            if entry.get("signal_ref") is not None:
                identitaet = db.resolve_identity(sid, quelle=source, signal_ref=entry["signal_ref"])
                if identitaet is None:
                    raise ValueError("Interne Signalreferenz des Prüfauftrags ist nicht belegt.")
            version = str(entry.get("quelle_version") or "").strip().lower()
            if not version:
                raise ValueError("Eindeutige Quellen-/Plattformversion fehlt.")
            cli = quellen.client_fuer_quelle(quelle)
            if source == "robo":
                if version not in {"mql4", "mql5", "rst"}:
                    raise ValueError("Unbekannte Robo-Plattform in der Quellenprofitabilität.")
                self.log(f"robo:{sid}: Gewinn und Rendite aus Quellenkennzahlen lesen …")
                raw = ingest.hole_metrics(quelle, sid, version, client=cli, allow_offline_cache=False)
                self._stop(should_stop)
                result.update(robo_quellenwerte(raw, sid, version))
                return _json_sicher(result)
            self.log(f"{source}:{sid}: aktuelle vollständige Quelldaten beschaffen …")
            refresh = cli.refresh_provider(sid, version, should_stop=should_stop)
            self._stop(should_stop)
            # Der Client prüft Jobidentität und Datum. Der Service fordert
            # dieselben Belege nochmals, auch bei injizierten Testclients.
            if (not isinstance(refresh, dict) or str(refresh.get("providerId")) != str(sid)
                    or refresh.get("version") != version
                    or refresh.get("platformRefreshed") is not True
                    or refresh.get("fullHistory") is not True
                    or not refresh.get("jobId") or not refresh.get("refreshedAt")):
                raise ValueError("Kein Nachweis eines aktuellen vollständigen Abrufs dieses Anbieters.")
            result["refresh"] = refresh
            raw_metrics = ingest.hole_metrics(quelle, sid, version, client=cli,
                                               allow_offline_cache=False)
            if not isinstance(raw_metrics, dict):
                raise ValueError("Kennzahlenantwort ist kein belegtes Quellenobjekt.")
            for id_key in ("providerId", "signalId", "id"):
                if id_key in raw_metrics and str(raw_metrics[id_key]) != str(sid):
                    raise ValueError("Kennzahlen gehören zu einer anderen Anbieter-ID.")
            if (raw_metrics.get("version") is not None
                    and str(raw_metrics["version"]).strip().lower() != version):
                raise ValueError("Kennzahlen gehören zu einer anderen Quellen-/Plattformversion.")
            stats = ingest.metrics_zu_stats(raw_metrics, quelle_kuerzel=source,
                                            quelle_version=version)
            result["quellen_stats"] = stats
            currency = str(stats.get("account_currency") or "").strip().upper()
            result["account_currency"] = currency or None
            if currency != "USD":
                raise ValueError(f"Belegte USD-Kontowährung fehlt (geliefert: {currency or 'unbekannt'}).")
            if (stats.get("quelle_trade_history_complete") is False
                    or stats.get("quelle_trades_history_complete") is False
                    or stats.get("quelle_trades_gekappt")):
                raise ValueError("Die Quelle meldet unvollständige oder gekappte Trade-Historie.")
            self._stop(should_stop)
            path, _ = ingest.hole_trades(quelle, sid, version, client=cli,
                                        allow_offline_cache=False)
            path, digest = db.snapshot_trade_file(path)
            result.update(trades_path=path, trades_sha256=digest)
            parsed = parser.load_export(path)
            result["trades"] = len(parsed.trades)
            if not parsed.trades:
                raise ValueError("Keine abgeschlossenen Trades im aktuellen Export.")
            erste = min(trade.open_time for trade in parsed.trades)
            letzte = max(trade.close_time for trade in parsed.trades)
            result["dauer_monate"] = ((letzte - erste).total_seconds()
                                       / 86400.0 / portfolio_statistik.MONAT_TAGE)
            result.update(zeit_von=erste.isoformat(), zeit_bis=letzte.isoformat())
            initial = stats.get("initial_deposit_usd")
            if initial is not None and (_zahl(initial) is None or initial <= 0):
                raise ValueError("Gelieferte echte Kapitalbasis ist nicht positiv und endlich.")
            self._stop(should_stop)
            # Volle Engine, aber noch kein Terminalstart vor Kapitalprüfung.
            report = engine.analyze(path, broker=stats.get("broker_server"),
                                    kapitalbasis_usd=initial,
                                    kapitalbasis_quelle="signalseite_initial_deposit")
            result["forensik"] = report
            findings = report["forensics"]
            # Preserve proven findings even when a later capital/price check
            # cannot establish a return or an equity drawdown.
            excluded = next((item for item in config.load_known_signals().get("ausgeschlossen", [])
                             if identity_key(item) == (source, sid)), None)
            if excluded is not None:
                result.update(hard_excluded=True,
                              ausschlussgrund="Explizite Ausschlussliste: " + str(excluded.get("grund") or "Ausschluss"))
            if findings["martingale"].get("flag") is True:
                result.update(hard_excluded=True, ausschlussgrund="Martingale-Signatur durch Code belegt.")
            dd = findings["drawdown"]
            kapital = _zahl(dd.get("startkapital_raw"))
            if kapital is None or kapital <= 0:
                raise ValueError("Keine belegte positive echte Kapitalbasis; virtuelle 10.000-USD-Annahme ist ausgeschlossen.")
            if dd.get("startkapital_quelle") not in {"csv_einzahlungen", "signalseite_initial_deposit"}:
                raise ValueError("Kapitalbasis ist nicht als echte Einzahlung oder echter Initial Deposit belegt.")
            result["kapitalbasis_usd"] = kapital
            ok, grund = _kapitalbasis_abgleich(dd, stats)
            if not ok:
                raise ValueError(grund)
            material_ok, material_grund = pruefe_mindestmaterial(result["dauer_monate"], result["trades"])
            if not material_ok:
                db.verify_trade_file(path, digest)
                result["data_complete"] = True
                result["grund"] = material_grund
                return _json_sicher(result)
            self._stop(should_stop)
            provider = self._kurse()
            equity = _rekonstruiere_mit_feed_fallback(parsed, provider, kapital,
                                                      stats.get("broker_server"))
            equity["account_currency"] = currency
            result["equity"] = equity
            findings["equity_rekonstruktion"] = equity
            self._stop(should_stop)
            # Historische H1-FX-Quotes können erst nach der Equity-Abfrage
            # im gemeinsamen Cache liegen (CNH/ETH/BCH-Verträge).
            if findings["exposure"].get("conversion_complete") is not True:
                findings["exposure"] = exposure.run(parsed, broker=stats.get("broker_server"),
                    kapitalbasis_usd=initial, kapitalbasis_quelle="signalseite_initial_deposit",
                    kursanbieter=provider)
            exp = findings["exposure"]
            missing = [label for key, label in (
                ("contract_complete", "Kontraktbelege"),
                ("conversion_complete", "historische USD-Umrechnung"),
                ("capital_history_complete", "vollständige Kapitalhistorie"),
                ("temporal_risk_available", "belastbare Exposure-Messung"),
            ) if exp.get(key) is not True]
            if missing:
                raise ValueError("Pflichtforensik unvollständig: " + ", ".join(missing))
            equity_dd, grund = equity_nenner(equity, result["trades"])
            if equity_dd is None:
                raise ValueError(grund)
            result["equity_dd_pct"] = equity_dd
            eff = portfolio_statistik.effizienz_kennzahlen(path, kapital, equity_dd,
                                                           min_historie_monate=MIN_MONATE)
            if not eff or eff.get("effizienz_status") != "ok":
                raise ValueError("Rendite/RetDD nicht belegbar: " + str((eff or {}).get("effizienz_status") or "keine Renditebasis"))
            findings["effizienz_recherche"] = eff
            result.update({key: eff.get(key) for key in
                           ("retdd_jahr", "ertrag_monat_geom_pct", "cagr_jahr_pct", "dauer_monate")})
            # CAGR und tatsächliche Zeitspanne aus derselben TWR-Basis
            # zurückführen; kein Netto/Start bei späteren Einzahlungen.
            cagr = result["cagr_jahr_pct"]
            years = eff.get("dauer_jahre")
            if _zahl(cagr) is not None and cagr > -100 and _zahl(years) is not None:
                zeitraum = math.expm1(math.log1p(cagr / 100.0) * years) * 100.0
                result["rendite_zeitraum_pct"] = zeitraum
                result["retdd_zeitraum"] = zeitraum / equity_dd
            db.verify_trade_file(path, digest)
            result["data_complete"] = True
            result["eligible"], result["grund"] = pruefe_kriterien(result)
        except _Abbruch as error:
            result.update(eligible=False, grund=str(error), abgebrochen=True)
        except Exception as error:
            result.update(eligible=False, grund=f"{type(error).__name__}: {error}")
            if should_stop():
                result["abgebrochen"] = True
            self.log(result["grund"])
        return _json_sicher(result)
