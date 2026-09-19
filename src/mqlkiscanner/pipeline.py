# -*- coding: utf-8 -*-
"""Scan-Pipeline: Liste -> Kandidaten -> Daten+Forensik -> LLM (Phase 2/3).

Die Engine rechnet ALLE Zahlen; das LLM bekommt nur fertige Befunde als
JSON (AGENTS.md Design-Regel 1). Jeder Schritt meldet Fortschritt ueber
Callbacks, damit die GUI ihn visualisieren kann.

Lauf-Ergebnisse landen in data/runs/{zeitstempel}/results.json.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import traceback
from uuid import uuid4
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

import requests

from . import config, scoring
from . import db
from . import fx_rates
from .analysis_version import FORENSICS_VERSION
from .engine import analyze as analyze_export
from .llm import client as llm_client
from .llm import prompts as llm_prompts
from .mql5 import crawler, exporter, signal_stats
from .mql5.errors import Mql5CredentialsMissingError
from .mql5.ratelimit import Mql5HardStopError, is_hard_mql5_failure
from .mql5.session import Mql5Session

ProgressCb = Callable[[int, int, str], None]
LogCb = Callable[[str], None]


@dataclass
class StepLog:
    """Sammelt Log-Zeilen je Schritt fuer die GUI-Anzeige."""
    lines: list[str] = field(default_factory=list)

    def __call__(self, text: str) -> None:
        self.lines.append(text)


@dataclass
class ScanResult:
    """Ein Ergebnis-Datensatz je Signal fuer die GUI-Tabelle."""
    id: int
    name: str = ""
    platform: str = ""
    url: str = ""
    autor: str = ""
    abonnenten: float | None = None
    abo_preis_usd: float | None = None
    wochen: float | None = None
    growth_pct: float | None = None
    ertrag_monat_pct: float | None = None
    pf: float | None = None
    dd_equity_pct: float | None = None     # Plattform "By Equity"
    dd_balance_pct: float | None = None    # Plattform "By Balance"
    # Forensik (nur mit Trade-Export)
    forensik_vorhanden: bool = False
    forensik_version: int | None = None
    trading_dd_pct: float | None = None
    trading_dd_usd: float | None = None
    winrate_pct: float | None = None
    max_verlustserie: int | None = None
    verlustserie_usd: float | None = None
    peak_positionen: int | None = None
    peak_netto_lots: float | None = None
    shock_usd: float | None = None
    shock_pct_max: float | None = None
    shock_pct_peak_time: str | None = None
    shock_pct_peak_account: float | None = None
    shock_pct_peak_usd: float | None = None
    martingale_flag: bool | None = None
    martingale_evidenz: list | None = None
    stop_nachweis: str = ""
    stop_evidence: str | None = None  # direct | cluster | partial | none; nie aus Freitext ableiten
    broker_server: str | None = None
    symbole: str = ""               # gehandelte Assets ("XAUUSD, US30, ...")
    # Bewertung
    score: float | None = None
    schranke_verletzt: bool = False
    ampel: str = "⚪"
    urteil: str = "Vorprüfung (ohne Forensik)"
    # LLM-Teilergebnisse (Nutzer-Prinzip: 2 Analysen + 1 Gesamtauswertung)
    trades_path: str = ""           # Quelldatei der Trades (fuer Prompt 1)
    trades_sha256: str = ""         # Inhalt des unveränderlichen Trade-Snapshots
    berichte_basis: str = ""        # Datengrundlage der im Ergebnis enthaltenen KI-Texte
    bericht_hinweis: str = ""
    pdf_fehler: str = ""
    trade_analyse: str = ""         # Prompt 1: Strategie aus den Trades (glm-5.3)
    trade_analyse_at: str = ""
    trade_analyse_model: str = ""
    risiko_analyse: str = ""        # Prompt 2: Risiko-Profil aus Forensik (Flash)
    risiko_analyse_at: str = ""
    risiko_analyse_model: str = ""
    gesamtbericht: str = ""         # Prompt 3: ausfuehrlicher Gesamtbericht (glm-5.3)
    gesamtbericht_at: str = ""      # Erstellungszeitpunkt des enthaltenen Gesamtberichts
    gesamtbericht_model: str = ""
    kurzfassung: str = ""           # Kurzzeile aus dem Gesamtbericht (fuer Tabelle)
    llm_fehler: str = ""
    fehler: str = ""
    source_kind: str = "live"  # Demo-Ergebnisse nie in den Live-Katalog übernehmen.
    persisted_this_run: bool = False  # Mindestens ein Versuch dieses analyze_candidate-Aufrufs gespeichert.

    def to_row(self) -> dict:
        return {
            "Ampel": self.ampel, "ID": self.id, "Name": self.name,
            "Platform": self.platform, "Abo $": self.abo_preis_usd,
            "Abos": self.abonnenten, "Wochen": self.wochen,
            "Growth %": self.growth_pct, "Ertrag/Monat %": self.ertrag_monat_pct,
            "PF": self.pf, "EQ-DD %": self.dd_equity_pct,
            "Bal-DD %": self.dd_balance_pct, "Trading-DD %": self.trading_dd_pct,
            "Winrate %": self.winrate_pct,
            "Verlustserie": self.max_verlustserie,
            "Peak-Pos": self.peak_positionen,
            "Netto-Lots": self.peak_netto_lots,
            "Schock $": self.shock_usd,
            "Martingale": ("JA" if self.martingale_flag else
                           ("nein" if self.martingale_flag is not None else "")),
            "Stop": self.stop_nachweis, "Score": self.score,
            "Kurzfassung": self.kurzfassung, "Urteil": self.urteil,
            "Bericht vom": self.gesamtbericht_at or None,
            "Fehler": self.fehler,
        }


def results_from_db(settings: dict | None = None) -> list[ScanResult]:
    """Alle in der SQLite-DB gespeicherten Signale als ScanResult-Liste."""
    settings = {**config.load_settings(), **(settings or {})}
    results: list[ScanResult] = []
    for row in db.list_catalog():
        stats = row.get("stats") or {}
        f = row.get("forensik") or {}
        if not isinstance(f, dict):
            f = {}
        peak = f.get("peak_exposure") or {}
        trading = f.get("trading_dd") or {}
        # Flaches Alt-Schema aus analyze_local_files (trading_dd_pct ohne Nesting).
        if not trading and f.get("trading_dd_pct") is not None:
            trading = {"pct": f.get("trading_dd_pct"), "usd": f.get("trading_dd_usd")}
        last_fehler = stats.get("last_fehler")
        signal_updated = row.get("signal_updated") or ""
        forensik_updated = row.get("forensik_updated") or ""
        forensik_ok = stats.get("forensik_ok")
        # Teilergebnis-Payloads (vollstaendig=False): Werte zeigen, aber nicht
        # als vollstaendige Forensik werten — der Grund steht im Fehlerfeld.
        vollstaendig = f.get("vollstaendig", True)
        # Aktuelle Forensik nur, wenn der letzte Scan sie explizit bestanden hat.
        # Legacy (ohne forensik_ok): last_fehler + Zeitstempel (>= wegen Sekundenaufloesung).
        if forensik_ok is False:
            forensik_stale = bool(f) and vollstaendig
        elif forensik_ok is True:
            forensik_stale = False
        else:
            forensik_stale = bool(last_fehler) and (
                not f or not forensik_updated or signal_updated >= forensik_updated
            )
        version_current = (f.get("version") == FORENSICS_VERSION
                           and stats.get("forensik_version") == FORENSICS_VERSION
                           and peak.get("shock_pct_max") is not None)
        # Unvollstaendige Teilergebnisse sind bekannt-begruendet, nicht "veraltet".
        version_stale = bool(f) and not version_current and vollstaendig
        forensik_stale = forensik_stale or version_stale
        res = ScanResult(
            id=int(row["signal_id"]),
            source_kind="demo" if row.get("platform") == "CSV" else "live",
            name=row.get("name") or str(row["signal_id"]),
            platform=row.get("platform") or "",
            url=row.get("url") or "",
            autor=row.get("autor") or "",
            abonnenten=row.get("abonnenten"),
            abo_preis_usd=row.get("abo_preis"),
            wochen=row.get("wochen"),
            growth_pct=stats.get("growth_pct"),
            ertrag_monat_pct=stats.get("ertrag_monat_pct"),
            pf=stats.get("pf"),
            dd_equity_pct=stats.get("eq_dd_pct"),
            dd_balance_pct=stats.get("bal_dd_pct"),
            forensik_vorhanden=bool(f) and vollstaendig and not forensik_stale,
            forensik_version=f.get("version"),
            trading_dd_pct=trading.get("pct", f.get("trading_dd_pct")),
            trading_dd_usd=trading.get("usd", f.get("trading_dd_usd")),
            winrate_pct=f.get("winrate_pct"),
            max_verlustserie=f.get("max_verlustserie"),
            verlustserie_usd=f.get("verlustserie_usd"),
            peak_positionen=peak.get("positionen", f.get("peak_positionen")),
            peak_netto_lots=peak.get("netto_lots", f.get("peak_netto_lots")),
            shock_usd=peak.get("schock_usd", f.get("shock_usd")),
            shock_pct_max=peak.get("shock_pct_max"),
            shock_pct_peak_time=peak.get("shock_pct_peak_time"),
            shock_pct_peak_account=peak.get("shock_pct_peak_account"),
            shock_pct_peak_usd=peak.get("shock_pct_peak_usd"),
            martingale_flag=f.get("martingale_flag"),
            martingale_evidenz=f.get("martingale_evidenz") or [],
            stop_nachweis=f.get("stop_nachweis") or "",
            stop_evidence=f.get("stop_evidence"),
            broker_server=stats.get("broker_server"),
            symbole=f.get("symbole") or "",
            score=None if forensik_stale else f.get("score"),
            trades_path=row.get("trades_path") or "",
            trades_sha256=row.get("trades_sha256") or "",
            trade_analyse=row.get("trade_analyse") or "",
            trade_analyse_at=row.get("trade_at") or "",
            trade_analyse_model=row.get("trade_model") or "",
            risiko_analyse=row.get("risiko_analyse") or "",
            risiko_analyse_at=row.get("risiko_at") or "",
            risiko_analyse_model=row.get("risiko_model") or "",
            gesamtbericht=row.get("gesamtbericht") or "",
            gesamtbericht_at=row.get("gesamt_at") or "",
            gesamtbericht_model=row.get("gesamt_model") or "",
            fehler=last_fehler or "",
        )
        if forensik_stale and f:
            res.urteil = (f"Veraltete Forensik nach fehlgeschlagenem Neu-Lauf "
                          f"({last_fehler})")
        if res.dd_equity_pct is not None or res.trading_dd_pct is not None:
            limit = float(settings.get("schranke_eq_dd_pct", 30.0))
            eq = float(res.dd_equity_pct) if res.dd_equity_pct is not None else 0.0
            real = float(res.trading_dd_pct) if res.trading_dd_pct is not None else 0.0
            res.schranke_verletzt = max(eq, real) > limit
        if res.gesamtbericht:
            res.kurzfassung = _extract_kurzfassung(res.gesamtbericht)
        if any((res.trade_analyse, res.risiko_analyse, res.gesamtbericht)):
            try:
                from .pdf_reports import materialize_result_pdfs
                materialize_result_pdfs(res)
            except Exception as exc:
                res.pdf_fehler = f"PDF-Speicherung fehlgeschlagen: {type(exc).__name__}: {exc}"
        res.ampel, res.urteil = ampel_for(res, settings)
        if forensik_stale and last_fehler:
            res.urteil = f"Fehler (Forensik veraltet): {last_fehler}"
        elif forensik_stale:
            res.urteil = "Forensik veraltet oder unvollständig — erneute Prüfung erforderlich."
        restore_current_reports(res, settings)
        results.append(res)
    return results


def ampel_for(result: ScanResult, settings: dict) -> tuple[str, str]:
    """Risiko VOR Ertrag; Grün erfordert Forensik und belastbare Stop-Evidenz.

    Bewiesene rote Flags (Martingale-Signatur aus dem Trade-Muster) gelten
    auch bei sonst unvollständiger Forensik — Kapitalbasis braucht dafuer
    niemand. Alles andere bleibt ohne vollstaendige Batterie Vorprüfung.
    """
    known = config.load_known_signals()
    excluded = {e["id"]: e for e in known.get("ausgeschlossen", [])}
    if result.id in excluded:
        return "⛔", f"Ausgeschlossen (Liste): {excluded[result.id].get('grund', '')}"
    if result.martingale_flag:
        return "🔴", "Martingale-Signatur nachgewiesen (Ablehnung)"
    if result.fehler and not result.forensik_vorhanden:
        return "⚪", f"Fehler: {result.fehler}"
    if result.fehler:
        return "⚪", f"Prüfung mit Fehler: {result.fehler}"
    if result.schranke_verletzt:
        limit = settings.get("schranke_eq_dd_pct", 30)
        return "🔴", f"Schranke verletzt: Drawdown > {limit:g} % (harte Ablehnung)"
    if result.forensik_vorhanden:
        if result.stop_evidence not in ("direct", "cluster"):
            reason = ("Stop-Nachweis nur teilweise vorhanden" if result.stop_evidence == "partial"
                      else "Kein belastbarer Stop-Nachweis")
            return "🟡", f"{reason} (kein Kandidat)"
        if result.score is not None and result.score < 5.0:
            min_return = settings.get("min_ertrag_pct_monat", 5.0)
            if (result.ertrag_monat_pct or 0) >= min_return:
                return "🟢", "Kandidat: Forensik bestanden, Stop-Evidenz vorhanden, Score < 5, Ertrag ok"
            return "🟡", f"Forensik ok, aber Ertrag < {min_return:g} %/Monat"
        return "🟡", f"Forensik bestanden, Score {result.score} (kein Kandidat)"
    return "⚪", "Vorprüfung (ohne Trade-Export-Forensik)"


def _kriterien_text(settings: dict) -> str:
    return (f"- Harte Schranke: max. {settings.get('schranke_eq_dd_pct', 30)} % Equity-Drawdown\n"
            f"- Mindest-Ertrag: {settings.get('min_ertrag_pct_monat', 5)} %/Monat\n"
            "- Risiko VOR Ertrag; Stop-Loss muss BEWIESEN sein (Orderbuch oder "
            "eindeutige Cluster-Signatur), nicht nur behauptet\n"
            "- Keine positive Einstufung vor vollstaendiger Forensik-Batterie")


def _kandidat_json(r: ScanResult) -> str:
    """Kandidaten-Kennzahlen als JSON (LLM-Payload, AGENTS.md Design-Regel 1)."""
    return json.dumps({
        "id": r.id, "name": r.name, "platform": r.platform,
        "autor": r.autor, "url": r.url,
        "wochen": r.wochen, "abonnenten": r.abonnenten,
        "abo_preis_usd": r.abo_preis_usd,
        "growth_pct": r.growth_pct, "ertrag_monat_pct": r.ertrag_monat_pct,
        "pf": r.pf, "dd_equity_pct": r.dd_equity_pct,
        "dd_balance_pct": r.dd_balance_pct,
        "broker_server": r.broker_server,
        "assets": r.symbole,
        "score_engine": r.score, "ampel": r.ampel,
        "schranke_verletzt": r.schranke_verletzt,
    }, ensure_ascii=False)


def _forensik_json(r: ScanResult) -> str:
    """Engine-Forensik als JSON (LLM-Payload, AGENTS.md Design-Regel 1)."""
    return json.dumps({
        "trading_dd": {"pct": r.trading_dd_pct, "usd": r.trading_dd_usd},
        "winrate_pct": r.winrate_pct,
        "max_verlustserie": r.max_verlustserie,
        "verlustserie_usd": r.verlustserie_usd,
        "peak_exposure": {"positionen": r.peak_positionen,
                          "netto_lots": r.peak_netto_lots,
                          "schock_usd": r.shock_usd,
                          "shock_pct_max": r.shock_pct_max,
                          "shock_pct_peak_time": r.shock_pct_peak_time,
                          "shock_pct_peak_account": r.shock_pct_peak_account,
                          "shock_pct_peak_usd": r.shock_pct_peak_usd},
        "martingale_flag": r.martingale_flag,
        "martingale_evidenz": r.martingale_evidenz,
        "stop_nachweis": r.stop_nachweis,
        "stop_evidence": r.stop_evidence,
    }, ensure_ascii=False)


def _stop_evidence_text(stops: dict) -> str:
    if stops.get("evidence_level") == 1:
        if "positions_with_sl" in stops:
            return f"Orderbuch: {stops['positions_with_sl']}/{stops.get('positions_total')} mit SL"
        return (f"Orderbuch: {stops.get('positions_with_sl_tp')}/"
                f"{stops.get('positions_total')} mit SL/TP")
    return stops.get("verdict", "kein Nachweis")


def report_basis_for(result: ScanResult, settings: dict) -> str | None:
    """Stable identity of the facts and criteria used for signal reports.

    Timestamps and storage paths are not evidence: identical CSV bytes and
    facts may reuse a report, while changed risk inputs must not do so.
    """
    csv_hash = result.trades_sha256
    if not csv_hash and result.trades_path:
        try:
            csv_hash = db.file_sha256(result.trades_path)
        except OSError:
            return None
    facts = json.loads(_kandidat_json(result))
    # Derived display fields are reconstructed from the same facts/criteria.
    facts.pop("ampel", None)
    facts.pop("schranke_verletzt", None)
    forensics = json.loads(_forensik_json(result))
    forensics["martingale_evidenz"] = result.martingale_evidenz or []
    content = {
        "format": 1, "version": result.forensik_version,
        "implementation_version": FORENSICS_VERSION,
        "forensics_complete": result.forensik_vorhanden,
        "csv_sha256": csv_hash, "facts": facts, "forensics": forensics,
        "exclusion": next((entry for entry in config.load_known_signals().get("ausgeschlossen", [])
                           if entry["id"] == result.id), None),
        "criteria": {key: settings.get(key, config.DEFAULT_SETTINGS[key])
                     for key in ("schranke_eq_dd_pct", "min_ertrag_pct_monat")},
    }

    def canonical(value):
        if isinstance(value, dict):
            return {key: canonical(item) for key, item in value.items()}
        if isinstance(value, list):
            return [canonical(item) for item in value]
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value) if value else 0.0  # SQLite REAL vs. parsed integer
        return value

    encoded = json.dumps(canonical(content), sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def refresh_report_verdict(result: ScanResult, settings: dict) -> None:
    """Recompute settings-dependent flags before using a current report or prompt."""
    if result.dd_equity_pct is not None or result.trading_dd_pct is not None:
        limit = float(settings.get("schranke_eq_dd_pct", 30.0))
        result.schranke_verletzt = max(result.dd_equity_pct or 0.0,
                                      result.trading_dd_pct or 0.0) > limit
    result.ampel, result.urteil = ampel_for(result, settings)


def restore_current_reports(result: ScanResult, settings: dict) -> bool:
    """Load only analyses bound to the current evidence; retain history in SQLite."""
    if result.forensik_vorhanden and not result.fehler:
        refresh_report_verdict(result, settings)
    basis = report_basis_for(result, settings) if result.forensik_vorhanden and not result.fehler else None
    stale = False
    for kind in ("trade_analyse", "risiko_analyse", "gesamtbericht"):
        previous = db.get_latest_analysis(result.id, kind)
        current = db.get_latest_analysis(result.id, kind, basis=basis) if basis else None
        setattr(result, kind, current["text"] if current else "")
        setattr(result, f"{kind}_at", (current["created_at"] or "") if current else "")
        setattr(result, f"{kind}_model", (current["model"] or "") if current else "")
        stale = stale or bool(previous and current is None)
    result.kurzfassung = _extract_kurzfassung(result.gesamtbericht)
    result.berichte_basis = basis or ""
    result.bericht_hinweis = (
        "Vorhandene KI-Berichte sind veraltet oder keiner geprüften Datengrundlage zugeordnet. "
        "Sie bleiben im Archiv bzw. in der Datenbank-Historie erhalten; aktuelle Berichte neu erstellen."
        if stale else "")
    return bool(result.gesamtbericht)


def _incomplete_forensics_reason(exposure: dict) -> str:
    warnings = exposure.get("warnings") or []
    if warnings:
        return " ".join(warnings)
    # Fallback mit konkreten Flags statt Sammelphrase — die Engine schreibt
    # normalerweise eine Warnung; dieser Zweig deckt Alt-Befunde ab.
    flags = [name for name, key in (
        ("Kapitalhistorie unvollständig", "capital_history_complete"),
        ("Kontraktspec fehlt", "contract_complete"),
        ("USD-Umrechnung fehlt", "conversion_complete"),
        ("kein belastbarer Schockanteil", "temporal_risk_available"),
    ) if exposure.get(key) is False]
    return ("; ".join(flags) + " — Details im Exposure-Befund.") if flags \
        else "Kapitalhistorie oder Pflichtbefunde fehlen."


class ScanPipeline:
    def __init__(self, settings: dict | None = None):
        self.settings = {**config.load_settings(), **(settings or {})}
        self.llm = llm_client.GlmClient(
            model_stufe1=self.settings.get("model_stufe1", config.MODEL_STUFE1),
            model_stufe2=self.settings.get("model_stufe2", config.MODEL_STUFE2),
            max_total_tokens=int(self.settings.get("llm_max_total_tokens", 200_000)),
            base_url=self.settings.get("glm_base_url") or None,
        )
        # Aufeinanderfolgende systemische MQL5-Fehler (Ban/Drossel/Login).
        self._mql5_hard_fails = 0
        self.fail_fast_after = max(1, int(self.settings.get("mql5_fail_fast_after", 3)))

    def _register_mql5_outcome(self, *, ok: bool, exc: BaseException | None = None,
                               log: LogCb | None = None) -> None:
        """Zaehlt Hard-Failures; wirft Mql5HardStopError ab Schwellwert."""
        if ok:
            self._mql5_hard_fails = 0
            return
        if exc is None or not is_hard_mql5_failure(exc):
            return
        self._mql5_hard_fails += 1
        msg = (f"MQL5-Hard-Failure {self._mql5_hard_fails}/"
               f"{self.fail_fast_after}: {type(exc).__name__}: {exc}")
        if log:
            log(msg)
        if self._mql5_hard_fails >= self.fail_fast_after:
            raise Mql5HardStopError(
                f"Fail-Fast: {self._mql5_hard_fails} systemische MQL5-Fehler "
                f"in Folge — weitere Exporte gestoppt, um den Account zu schützen. "
                f"Letzter Fehler: {exc}") from exc

    # ------------------------------------------------------ Schritt 1 + 2
    def crawl(self, on_progress: ProgressCb, log: LogCb) -> list[dict]:
        session = Mql5Session(self.settings)
        signals = crawler.crawl_lists(
            session, seiten_pro_liste=int(self.settings.get("listen_seiten", 2)),
            on_progress=on_progress)
        log(f"{len(signals)} Signale geladen (MT4+MT5, "
            f"{self.settings.get('listen_seiten', 2)} Seiten je Liste).")
        return signals

    def build_candidates(self, signals: list[dict], log: LogCb) -> list[dict]:
        min_abo = int(self.settings.get("min_abonnenten", 0))
        min_wochen = float(self.settings.get("min_wochen", 26))
        candidates = []
        for s in signals:
            weeks = s.get("wochen")
            if weeks is not None and weeks < min_wochen:
                continue
            if (s.get("abonnenten") or 0) < min_abo:
                continue
            candidates.append(s)
        log(f"Vorfilter (Wochen >= {min_wochen:g}, Abonnenten >= {min_abo}): "
            f"{len(signals)} -> {len(candidates)} Kandidaten.")
        known = config.load_known_signals()
        excluded = {e["id"] for e in known.get("ausgeschlossen", [])}
        out_file = config.DATA_DIR / "candidates.json"
        out_file.write_text(json.dumps(candidates, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        log(f"Kandidatenliste gespeichert: {out_file} "
            f"({len(excluded)} Ausschluesse aus known_signals.json werden markiert).")
        return candidates

    # ------------------------------------------------------ Schritt 3
    def analyze_candidate(self, session: Mql5Session, cand: dict,
                          log: LogCb,
                          should_stop: Callable[[], bool] | None = None) -> ScanResult:
        """Einzelprüfung einmal wiederholen; Hard-Stop-Ausnahmen durchreichen."""
        result = self._analyze_candidate_once(session, cand, log)
        if not result.fehler:
            return result
        log(f"Signal {result.id}: Prüfung fehlgeschlagen — einmalige Wiederholung "
            "in 5 Sekunden (Versuch 2/2).")
        for _ in range(10):
            if should_stop and should_stop():
                log(f"Signal {result.id}: Wiederholung wegen Stop-Anforderung ausgelassen.")
                return result
            time.sleep(0.5)
        if should_stop and should_stop():
            log(f"Signal {result.id}: Wiederholung wegen Stop-Anforderung ausgelassen.")
            return result
        persisted_before_retry = result.persisted_this_run
        try:
            result = self._analyze_candidate_once(session, cand, log)
        except Mql5HardStopError as exc:
            if exc.result is not None:
                exc.result.persisted_this_run |= persisted_before_retry
            raise
        result.persisted_this_run |= persisted_before_retry
        log(f"Signal {result.id}: " + (
            "Auch Versuch 2/2 fehlgeschlagen; keine weitere Wiederholung."
            if result.fehler else "Wiederholung erfolgreich."))
        return result

    def _analyze_candidate_once(self, session: Mql5Session, cand: dict,
                          log: LogCb) -> ScanResult:
        res = ScanResult(id=cand["id"], name=cand.get("name") or str(cand["id"]),
                         platform=cand.get("platform") or "", url=cand.get("url", ""),
                         autor=cand.get("autor") or "",
                         abonnenten=cand.get("abonnenten"),
                         abo_preis_usd=cand.get("abo_preis_usd"),
                         wochen=cand.get("wochen"), growth_pct=cand.get("growth_pct"))
        try:
            log("Kennzahlen-Seite laden (mql5) …")
            stats = signal_stats.fetch_signal_stats(session, res.id)
            res.dd_equity_pct = stats.get("dd_equity_pct")
            res.dd_balance_pct = stats.get("dd_balance_pct")
            res.ertrag_monat_pct = stats.get("monthly_growth_pct")
            res.pf = stats.get("profit_factor")
            if res.wochen is None:
                res.wochen = stats.get("weeks")
            res.broker_server = stats.get("broker_server")
            log(f"✓ Kennzahlen: EQ-DD {res.dd_equity_pct} % · PF {res.pf} · "
                f"Ertrag {res.ertrag_monat_pct} %/Monat")
            # Eine öffentliche Kennzahlen-Seite belegt keinen funktionierenden
            # authentifizierten Export. Dessen Fehlerkette hier nicht zurücksetzen.

            log("Trade-Export laden (CSV) …")
            report = None
            try:
                try:
                    path, from_cache = exporter.export_positions(
                        session, res.id,
                        extra_pause_s=float(self.settings.get(
                            "rate_pause_zwischen_signalen_s", 5.0)),
                        platform=res.platform or cand.get("platform"))
                except (Mql5HardStopError, Mql5CredentialsMissingError):
                    raise
                except (RuntimeError, requests.HTTPError):
                    # MQL5 drosselt / falscher Export-Pfad — Chrome-Fallback
                    # (History-Link auf der Signal-Seite, MT4+MT5).
                    log("Direkter Abruf fehlgeschlagen — Download über Chrome "
                        "(MqlDownloader-Muster) …")
                    from .mql5.browser_session import export_positions_via_browser
                    path = export_positions_via_browser(res.id, log=log)
                    from_cache = False
                res.trades_path = path
                with open(path, encoding="utf-8") as fh:
                    n_lines = sum(1 for _ in fh)
                log(f"✓ Trade-Export: {n_lines} Zeilen "
                    f"({'Cache' if from_cache else 'neu geladen'})")
                log("Forensik-Batterie (4 Tests) läuft …")
                # EZB-Kurse vorwaermen (Download beim ersten Bedarf) und den
                # Stand ins Protokoll nehmen — FX-Kreuze brauchen sie zur
                # USD-Umrechnung; offline bleibt die Umrechnung ehrlich gesperrt.
                ezb = fx_rates.status()
                log("EZB-Referenzkurse: " + (
                    f"geladen bis {ezb.get('letzte_kursdatum')}" if ezb.get("geladen")
                    else "nicht verfuegbar (offline?) — FX-Kreuze bleiben ohne USD-Schock"))
                # Broker mitgeben: cross_broker=false-Kontraktspecs (z. B. Oel)
                # gelten nur fuer den gelisteten Broker des Signals.
                report = analyze_export(path, broker=res.broker_server)
            except Mql5CredentialsMissingError:
                log("Trade-Export übersprungen (kein MQL5-Login) — "
                    "Vorprüfung ohne Forensik. Login im Admin-Bereich ergänzen.")
            if report is not None:
                st, fx = report["stats"], report["forensics"]
                if not st.get("trades"):
                    raise ValueError("Forensik unvollständig: keine abgeschlossenen Trades im Export.")
                res.forensik_vorhanden = True
                res.symbole = ", ".join(sorted(st.get("symbols", {})))
                td = fx["drawdown"]["trading_dd"]
                # Risiko-/Ampel-% = max. relativer DD; USD-Anker bleibt dd_usd.
                res.trading_dd_pct = td.get("dd_pct_max_rel", td.get("dd_pct"))
                res.trading_dd_usd = td["dd_usd"]
                res.winrate_pct = st.get("winrate_pct")
                res.max_verlustserie = st.get("max_consecutive_losses")
                res.verlustserie_usd = st.get("max_consecutive_losses_sum")
                expo = fx["exposure"]
                res.peak_positionen = expo.get("peak_open_positions")
                res.peak_netto_lots = expo.get("peak_net_lots")
                res.shock_usd = expo.get("shock_usd")
                res.shock_pct_max = expo.get("shock_pct_max")
                res.shock_pct_peak_time = expo.get("shock_pct_peak_time")
                res.shock_pct_peak_account = expo.get("shock_pct_peak_account")
                res.shock_pct_peak_usd = expo.get("shock_pct_peak_usd")
                res.martingale_flag = fx["martingale"].get("flag")
                res.martingale_evidenz = fx["martingale"].get("evidence") or []
                stops = fx["stops"]
                res.stop_nachweis = _stop_evidence_text(stops)
                res.stop_evidence = stops.get("stop_evidence")
                log(f"✓ Forensik: Winrate {res.winrate_pct} % · Trading-DD "
                    f"{res.trading_dd_pct} % · Serie {res.max_verlustserie} · "
                    f"Peak {res.peak_positionen} Pos · Martingale "
                    f"{'JA' if res.martingale_flag else 'nein'} · Stop: "
                    f"{res.stop_nachweis[:40]}")

                log("Risiko-Score berechnen …")
                platform = {
                    "eq_dd_pct": res.dd_equity_pct or 0,
                    "weeks": res.wochen,
                    "broker_risk": 5.0,      # Default offshore; Detailpruefung manuell
                    "transparency_risk": 5.0,
                }
                ev = scoring.evaluate(
                    report, platform=platform,
                    schranke_eq_dd_pct=self.settings.get("schranke_eq_dd_pct", 30.0))
                res.score = ev["score"]
                res.schranke_verletzt = bool(ev["schranke_eq_dd_verletzt"])
                res.forensik_vorhanden = bool(ev["forensics_complete"])
                if not res.forensik_vorhanden:
                    raise ValueError(f"Forensik unvollständig: {_incomplete_forensics_reason(expo)}")
                res.forensik_version = FORENSICS_VERSION
                self._register_mql5_outcome(ok=True)
        except Exception as exc:  # Ein weicher Fehler soll den Lauf nicht abbrechen
            res.fehler = f"{type(exc).__name__}: {exc}"
            res.forensik_vorhanden = False
            log(f"  FEHLER bei {res.id}: {res.fehler}")
            log(traceback.format_exc(limit=3))
            if isinstance(exc, Mql5HardStopError):
                # Stop further network work immediately, but preserve the current
                # failed scan just like a stop raised by the failure counter.
                hard_stop = exc
            else:
                try:
                    self._register_mql5_outcome(ok=False, exc=exc, log=log)
                    hard_stop = None
                except Mql5HardStopError as stop:
                    hard_stop = stop
        else:
            hard_stop = None
        # Alles in die Datenbank (Nutzer-Prinzip: CSV + MQL5-Infos + Befunde)
        try:
            # A public drawdown breach already rules out a signal, even when
            # the authenticated export was skipped and no score was computed.
            refresh_report_verdict(res, self.settings)
            db.init_db()
            stats_payload = {
                "eq_dd_pct": res.dd_equity_pct,
                "bal_dd_pct": res.dd_balance_pct,
                "ertrag_monat_pct": res.ertrag_monat_pct,
                "pf": res.pf, "growth_pct": res.growth_pct,
                "broker_server": res.broker_server,
                # Expliziter Vollstaendigkeitsstatus (verhindert Gruen aus alter Forensik).
                "forensik_ok": bool(res.forensik_vorhanden),
                "forensik_version": res.forensik_version,
            }
            if res.fehler and not res.forensik_vorhanden:
                stats_payload["last_fehler"] = res.fehler
            else:
                stats_payload["last_fehler"] = None
            if not res.forensik_vorhanden and not res.fehler:
                stats_payload["export_skipped"] = "no_credentials_or_no_export"
            ampel, grund = ampel_for(res, self.settings)
            res.ampel = ampel
            detail = (f" | Score {res.score}, Trading-DD {res.trading_dd_pct} %, "
                      f"Serie {res.max_verlustserie}, Peak {res.peak_positionen} Pos"
                      if res.forensik_vorhanden and res.trading_dd_pct is not None else "")
            res.urteil = grund + detail
            forensik_payload = None
            # Auch unvollstaendige Laeufe speichern ihre Teilergebnisse
            # (vollstaendig=False): Winrate/DD/Martingale/Stop bleiben sichtbar
            # und laden nach App-Neustart aus der DB; bewerten darf sie nur
            # als Vorprüfung bzw. rote Flag — nie als Kandidat.
            if res.forensik_vorhanden or res.winrate_pct is not None:
                forensik_payload = {
                    "version": FORENSICS_VERSION,
                    "vollstaendig": bool(res.forensik_vorhanden),
                    "trading_dd": {"pct": res.trading_dd_pct, "usd": res.trading_dd_usd},
                    "winrate_pct": res.winrate_pct,
                    "max_verlustserie": res.max_verlustserie,
                    "verlustserie_usd": res.verlustserie_usd,
                    "peak_exposure": {"positionen": res.peak_positionen,
                                      "netto_lots": res.peak_netto_lots,
                                      "schock_usd": res.shock_usd,
                                      "shock_pct_max": res.shock_pct_max,
                                      "shock_pct_peak_time": res.shock_pct_peak_time,
                                      "shock_pct_peak_account": res.shock_pct_peak_account,
                                      "shock_pct_peak_usd": res.shock_pct_peak_usd},
                    "martingale_flag": res.martingale_flag,
                    "martingale_evidenz": res.martingale_evidenz,
                    "stop_nachweis": res.stop_nachweis,
                    "stop_evidence": res.stop_evidence,
                    "symbole": res.symbole,
                    "fx_kursquelle": expo.get("fx_conversion", {}).get("quelle"),
                    # Score nur bei vollstaendiger Forensik — Design-Regel:
                    # kein Score vor bestandener Batterie.
                    "score": res.score if res.forensik_vorhanden else None,
                    "ampel": res.ampel}
            saved_trades_path = db.store_scan_result(res.id, {
                "name": res.name, "platform": res.platform, "url": res.url,
                "autor": res.autor, "abo_preis": res.abo_preis_usd,
                "abonnenten": res.abonnenten, "wochen": res.wochen,
                "stats": stats_payload,
            }, trades_path=res.trades_path, forensik=forensik_payload)
            res.persisted_this_run = True
            if saved_trades_path:
                res.trades_path = saved_trades_path
                res.trades_sha256 = db.file_sha256(saved_trades_path)
        except Exception as exc:  # DB-Fehler darf den Lauf nicht abbrechen
            storage_error = f"Speichern fehlgeschlagen: {type(exc).__name__}: {exc}"
            res.fehler = f"{res.fehler} | {storage_error}" if res.fehler else storage_error
            log(f"  DB-Fehler bei {res.id}: {exc}")
            ampel, grund = ampel_for(res, self.settings)
            res.ampel = ampel
            detail = (f" | Score {res.score}, Trading-DD {res.trading_dd_pct} %, "
                      f"Serie {res.max_verlustserie}, Peak {res.peak_positionen} Pos"
                      if res.forensik_vorhanden and res.trading_dd_pct is not None else "")
            res.urteil = grund + detail
        if hard_stop is not None:
            hard_stop.result = res
            raise hard_stop
        return res

    # ------------------------------------------------------ Schritt 4
    def run_llm(self, results: list[ScanResult], log: LogCb,
                on_progress: ProgressCb | None = None,
                should_stop: Callable[[], bool] | None = None) -> dict:
        """Drei-Stufen-Auswertung (Nutzer-Prinzip):

        Prompt 1  Trade-Analyse   — Strategie ANHAND DER TRADES ermitteln
                                    (starkes Modell, glm-5.3)
        Prompt 2  Risiko-Analyse  — Risikoprofil aus Forensik-Kennzahlen (Flash)
        Prompt 3  Gesamtbericht   — wertet ALLE Teilergebnisse aus, ausfuehrlich
                                    (starkes Modell, glm-5.3)

        Prompt 1 und 2 laufen parallel; Prompt 3 erst danach.
        Jedes Teilergebnis landet in der Datenbank (Tabelle analyses).
        Fortschritt zählt ausschließlich fertig gespeicherte Prompts. Start-
        und Fehlermeldungen verändern den Zähler nicht. Der Rückgabewert trennt
        erfolgreiche, fehlgeschlagene und nicht ausgeführte Prompts.
        should_stop: kooperativer Stopp (Stop-Button) — wird zwischen Kandidaten
        und vor dem Gesamtbericht geprüft; laufende Modellaufrufe laufen zu Ende.
        """
        from .llm_runner import run_llm
        return run_llm(self, results, log, on_progress, should_stop)

    # ------------------------------------------------------ Schritt 5
    PORTFOLIO_ANALYSIS_ID = None  # Globaler Bericht ohne Fremdschlüssel auf ein Signal.

    def run_portfolio(self, results: list[ScanResult], log: LogCb,
                      on_progress: ProgressCb | None = None,
                      should_stop: Callable[[], bool] | None = None) -> dict:
        """Portfolio-Vorschlag ueber ALLE Ergebnisse (Station 5 der GUI).

        Das LLM sieht je Signal: Kennzahlen, Forensik, Assets, Kurzfassung
        und den vollstaendigen Gesamtbericht — und schlaegt eine
        diversifizierte Depot-Kombination vor (Risiko vor Ertrag). Der
        Bericht landet in der DB unter signal_id=NULL, kind='portfolio'.
        """
        total = 1
        jobs = [r for r in results
                if r.source_kind == "live" and r.forensik_vorhanden and not r.fehler]
        if not self.llm.has_key:
            log("Portfolio übersprungen: kein GLM-Key gesetzt (Admin-Bereich).")
            if on_progress:
                on_progress(0, total, "Übersprungen: kein GLM-Key konfiguriert")
            return {"text": "", "reason": "Kein GLM-Key konfiguriert"}
        if not jobs:
            if on_progress:
                on_progress(0, total, "Übersprungen: keine geeigneten Forensik-Ergebnisse")
            return {"text": "", "reason": "Keine geeigneten Forensik-Ergebnisse"}
        kriterien = _kriterien_text(self.settings)
        eintraege = []
        for r in jobs:
            refresh_report_verdict(r, self.settings)
            if r.berichte_basis != report_basis_for(r, self.settings):
                restore_current_reports(r, self.settings)
            eintraege.append({
                "kandidat": json.loads(_kandidat_json(r)),
                "forensik": json.loads(_forensik_json(r)),
                "assets": r.symbole,
                "kurzfassung": r.kurzfassung,
                "gesamtbericht": r.gesamtbericht or "(nicht erstellt)",
            })
        prompt = (llm_prompts.load_prompt("portfolio")
                  .replace("{kandidaten_json}", json.dumps(eintraege, ensure_ascii=False))
                  .replace("{kriterien}", kriterien))
        model_strong = self.settings.get("model_stufe2", config.MODEL_STUFE2)
        log(f"→ Portfolio: {len(eintraege)} Signal-Berichte "
            f"({len(prompt):,} Zeichen) an {model_strong} …")
        if on_progress:
            on_progress(0, total,
                        f"Portfolio-Analyse über {len(eintraege)} Signale · "
                        "warte auf Modellantwort")
        if should_stop and should_stop():
            log("Stop angefordert — Portfolio-Analyse abgebrochen.")
            if on_progress:
                on_progress(0, total, "Abgebrochen: Stop-Anforderung")
            return {"text": "", "reason": "Abbruch per Stop-Button"}
        meta: dict = {}
        try:
            text = self.llm.chat(prompt, stufe=2, max_tokens=24576, meta_out=meta)
        except llm_client.LlmNoBalanceError as exc:
            log(f"Portfolio abgebrochen: {exc}")
            if on_progress:
                on_progress(0, total, f"Abgebrochen: {exc}")
            return {"text": "", "reason": str(exc)}
        except llm_client.LlmError as exc:
            log(f"  Portfolio-Fehler: {exc}")
            if on_progress:
                on_progress(0, total, f"Fehler: {exc}")
            return {"text": "", "reason": str(exc)}
        storage_error = ""
        try:
            db.store_analysis(self.PORTFOLIO_ANALYSIS_ID, "portfolio", model_strong,
                              self.llm.usage.total_tokens, text)
        except Exception as exc:  # DB-Fehler darf den Bericht nicht verlieren
            storage_error = f"Portfolio nicht in Datenbank gespeichert: {type(exc).__name__}: {exc}"
            log(f"  {storage_error}")
        log(f"  ✓ Portfolio-Vorschlag fertig: {meta.get('zeichen', '?')} Zeichen "
            f"in {meta.get('dauer_s', '?')}s — gesamt bisher: "
            f"{self.llm.usage.total_tokens:,} Tokens")
        if on_progress:
            on_progress(1, total, storage_error or "Portfolio-Vorschlag fertig")
        summary = {"text": text, "zeichen": meta.get("zeichen", len(text)),
                "tokens": self.llm.usage.total_tokens, "model": model_strong,
                "created_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
                "reason": storage_error, "storage_error": storage_error}
        try:
            from .pdf_reports import materialize_portfolio_pdf
            materialize_portfolio_pdf(summary)
        except Exception as exc:
            pdf_error = f"Portfolio-PDF nicht gespeichert: {type(exc).__name__}: {exc}"
            summary["storage_error"] = "; ".join(filter(None, (storage_error, pdf_error)))
            summary["reason"] = summary["storage_error"]
            log(f"  {pdf_error}")
        return summary

    # ------------------------------------------------------ Hilfen
    @staticmethod
    def analyze_local_files(files: list[str], settings: dict | None = None) -> list[ScanResult]:
        """Verifikations-/Demo-Modus: lokale CSVs (data/raw) durch die Engine."""
        settings = settings or {}
        results: list[ScanResult] = []
        known = config.load_known_signals()
        meta = {s["id"]: s for s in (known.get("empfehlung", []) + known.get("watchlist", []))}
        for path in files:
            try:
                report = analyze_export(path)
                if not report["stats"].get("trades"):
                    raise ValueError("Forensik unvollständig: keine abgeschlossenen Trades im Export.")
            except Exception as exc:
                r = ScanResult(id=0, source_kind="demo", name=path,
                               fehler=f"{type(exc).__name__}: {exc}")
                r.ampel, r.urteil = ampel_for(r, settings)
                results.append(r)
                continue
            st, fx = report["stats"], report["forensics"]
            sid = 0
            for sid_cand in (_extract_id(path),):
                if sid_cand and sid_cand in meta:
                    sid = sid_cand
            r = ScanResult(
                id=sid or (_extract_id(path) or 0),
                source_kind="demo",
                name=path.split("/")[-1].split("\\")[-1].replace("_", " "),
                platform="CSV",
                trades_path=path,
                wochen=st.get("span_weeks"),
                pf=st.get("profit_factor_csv"),
                forensik_vorhanden=True,
                trading_dd_pct=(fx["drawdown"]["trading_dd"].get("dd_pct_max_rel")
                                or fx["drawdown"]["trading_dd"]["dd_pct"]),
                trading_dd_usd=fx["drawdown"]["trading_dd"]["dd_usd"],
                winrate_pct=st.get("winrate_pct"),
                max_verlustserie=st.get("max_consecutive_losses"),
                verlustserie_usd=st.get("max_consecutive_losses_sum"),
                peak_positionen=fx["exposure"].get("peak_open_positions"),
                peak_netto_lots=fx["exposure"].get("peak_net_lots"),
                shock_usd=fx["exposure"].get("shock_usd"),
                shock_pct_max=fx["exposure"].get("shock_pct_max"),
                shock_pct_peak_time=fx["exposure"].get("shock_pct_peak_time"),
                shock_pct_peak_account=fx["exposure"].get("shock_pct_peak_account"),
                shock_pct_peak_usd=fx["exposure"].get("shock_pct_peak_usd"),
                martingale_flag=fx["martingale"].get("flag"),
                martingale_evidenz=fx["martingale"].get("evidence") or [],
                symbole=", ".join(sorted(st.get("symbols", {}))),
            )
            stops = fx["stops"]
            r.stop_nachweis = _stop_evidence_text(stops)
            r.stop_evidence = stops.get("stop_evidence")
            ev = scoring.evaluate(
                report, schranke_eq_dd_pct=settings.get("schranke_eq_dd_pct", 30.0))
            r.score = ev["score"]
            r.schranke_verletzt = ev["schranke_eq_dd_verletzt"]
            r.forensik_vorhanden = bool(ev["forensics_complete"])
            r.forensik_version = FORENSICS_VERSION if r.forensik_vorhanden else None
            if not r.forensik_vorhanden:
                r.fehler = f"Forensik unvollständig: {_incomplete_forensics_reason(fx['exposure'])}"
            if sid in meta:
                r.name = meta[sid].get("name", r.name)
                # Demo/Verifikation: kuratierte Referenzscores aus known_signals
                # ueberschreiben den Engine-Ist-Score (Kalibrierungsanker, nicht Live).
                curated = meta[sid].get("score")
                if curated is not None:
                    r.score = curated
                    r.urteil = ""  # ampel_for setzt neu; Kennzeichnung unten
                r.abo_preis_usd = meta[sid].get("abo_preis_usd")
                r.ertrag_monat_pct = meta[sid].get("monat_pct")
            r.ampel, grund = ampel_for(r, settings)
            if sid in meta and meta[sid].get("score") is not None:
                grund = f"{grund} | Score kuratiert ({r.score}, Engine {ev['score']})"
            r.urteil = grund + (f" | Trading-DD {r.trading_dd_pct} %"
                                if r.trading_dd_pct is not None else "")
            # Demo bleibt im Arbeitsspeicher bzw. separat im Laufarchiv.
            # Keine Live-Daten oder alten KI-Texte über dieselbe Signal-ID mischen.
            results.append(r)
        return results

    @staticmethod
    def save_run(results: list[ScanResult], logs: dict[str, list[str]],
                 portfolio: dict | None = None) -> str:
        from .pdf_reports import materialize_portfolio_pdf, materialize_result_pdfs
        portfolio = dict(portfolio) if portfolio is not None else None
        for result in results:
            try:
                materialize_result_pdfs(result)
                result.pdf_fehler = ""
            except Exception as exc:
                result.pdf_fehler = (
                    f"PDF-Speicherung fehlgeschlagen: {type(exc).__name__}: {exc}")
                logs.setdefault("pdf", []).append(
                    f"Signal #{result.id}: {result.pdf_fehler}")
        if portfolio and portfolio.get("text"):
            try:
                materialize_portfolio_pdf(portfolio)
            except Exception as exc:
                error = f"Portfolio-PDF nicht gespeichert: {type(exc).__name__}: {exc}"
                portfolio["storage_error"] = "; ".join(
                    filter(None, (portfolio.get("storage_error"), error)))
                logs.setdefault("pdf", []).append(error)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f") + "_" + uuid4().hex[:8]
        run_dir = config.RUNS_DIR / stamp
        run_dir.mkdir(parents=True, exist_ok=False)
        payload = {
            "zeitstempel": stamp,
            "ergebnisse": [vars(r) for r in results],
            "logs": logs,
            "portfolio": portfolio,
        }
        out = run_dir / "results.json"
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        # Archivleser sehen erst eine vollständige Datei, auch bei laufender UI.
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=run_dir,
                                             suffix=".tmp", delete=False) as fh:
                temporary = fh.name
                fh.write(text)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(temporary, out)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
        return str(out)


def _extract_id(path: str) -> int | None:
    import re
    m = re.search(r"(\d{6,7})", path)
    return int(m.group(1)) if m else None


def _extract_kurzfassung(bericht: str) -> str:
    """Zieht die Kurzzeile aus dem Gesamtbericht (fuer die Tabellenspalte)."""
    import re
    m = re.search(r"Kurzfassung\s*[:：]\s*(.+)", bericht)
    if m:
        return m.group(1).strip().strip("*").strip()
    return bericht.strip().splitlines()[0][:160] if bericht.strip() else ""
