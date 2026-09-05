# -*- coding: utf-8 -*-
"""Scan-Pipeline: Liste -> Kandidaten -> Daten+Forensik -> LLM (Phase 2/3).

Die Engine rechnet ALLE Zahlen; das LLM bekommt nur fertige Befunde als
JSON (AGENTS.md Design-Regel 1). Jeder Schritt meldet Fortschritt ueber
Callbacks, damit die GUI ihn visualisieren kann.

Lauf-Ergebnisse landen in data/runs/{zeitstempel}/results.json.
"""
from __future__ import annotations

import json
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from . import config, scoring
from . import db
from .engine import analyze as analyze_export
from .llm import client as llm_client
from .llm import prompts as llm_prompts
from .mql5 import crawler, exporter, signal_stats
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
    trading_dd_pct: float | None = None
    trading_dd_usd: float | None = None
    winrate_pct: float | None = None
    max_verlustserie: int | None = None
    verlustserie_usd: float | None = None
    peak_positionen: int | None = None
    peak_netto_lots: float | None = None
    shock_usd: float | None = None
    martingale_flag: bool | None = None
    martingale_evidenz: list | None = None
    stop_nachweis: str = ""
    broker_server: str | None = None
    # Bewertung
    score: float | None = None
    schranke_verletzt: bool = False
    ampel: str = "⚪"
    urteil: str = "Vorprüfung (ohne Forensik)"
    # LLM-Teilergebnisse (Nutzer-Prinzip: 2 Analysen + 1 Gesamtauswertung)
    trades_path: str = ""           # Quelldatei der Trades (fuer Prompt 1)
    trade_analyse: str = ""         # Prompt 1: Strategie aus den Trades (glm-5.3)
    risiko_analyse: str = ""        # Prompt 2: Risiko-Profil aus Forensik (Flash)
    gesamtbericht: str = ""         # Prompt 3: ausfuehrlicher Gesamtbericht (glm-5.3)
    kurzfassung: str = ""           # Kurzzeile aus dem Gesamtbericht (fuer Tabelle)
    llm_fehler: str = ""
    fehler: str = ""

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
            "Fehler": self.fehler,
        }


def ampel_for(result: ScanResult, settings: dict) -> tuple[str, str]:
    """Ampel-Logik: Risiko VOR Ertrag; keine positive Einstufung ohne Forensik."""
    known = config.load_known_signals()
    excluded = {e["id"]: e for e in known.get("ausgeschlossen", [])}
    if result.id in excluded:
        return "⛔", f"Ausgeschlossen (Liste): {excluded[result.id].get('grund', '')}"
    if result.fehler and not result.forensik_vorhanden:
        return "⚪", f"Fehler: {result.fehler}"
    if result.schranke_verletzt:
        return "🔴", "Schranke verletzt: EQ-DD > 30 % (harte Ablehnung)"
    if result.martingale_flag:
        return "🔴", "Martingale-Signatur nachgewiesen (Ablehnung)"
    if result.forensik_vorhanden:
        if result.score is not None and result.score < 5.0:
            if (result.ertrag_monat_pct or 0) >= settings.get("min_ertrag_pct_monat", 5.0):
                return "🟢", "Kandidat: Forensik bestanden, Score < 5, Ertrag ok"
            return "🟡", "Forensik ok, aber Ertrag < 5 %/Monat"
        return "🟡", f"Forensik bestanden, Score {result.score} (kein Kandidat)"
    return "⚪", "Vorprüfung (ohne Trade-Export-Forensik)"


def _kriterien_text(settings: dict) -> str:
    return (f"- Harte Schranke: max. {settings.get('schranke_eq_dd_pct', 30)} % Equity-Drawdown\n"
            f"- Mindest-Ertrag: {settings.get('min_ertrag_pct_monat', 5)} %/Monat\n"
            "- Risiko VOR Ertrag; Stop-Loss muss BEWIESEN sein (Orderbuch oder "
            "eindeutige Cluster-Signatur), nicht nur behauptet\n"
            "- Keine positive Einstufung vor vollstaendiger Forensik-Batterie")


class ScanPipeline:
    def __init__(self, settings: dict | None = None):
        self.settings = {**config.load_settings(), **(settings or {})}
        self.llm = llm_client.GlmClient(
            model_stufe1=self.settings.get("model_stufe1", config.MODEL_STUFE1),
            model_stufe2=self.settings.get("model_stufe2", config.MODEL_STUFE2),
            max_total_tokens=int(self.settings.get("llm_max_total_tokens", 200_000)),
            base_url=self.settings.get("glm_base_url") or None,
        )

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

            log("Trade-Export laden (CSV) …")
            path, from_cache = exporter.export_positions(
                session, res.id,
                extra_pause_s=float(self.settings.get("rate_pause_zwischen_signalen_s", 5.0)))
            res.trades_path = path
            with open(path, encoding="utf-8") as fh:
                n_lines = sum(1 for _ in fh)
            log(f"✓ Trade-Export: {n_lines} Zeilen "
                f"({'Cache' if from_cache else 'neu geladen'})")
            log("Forensik-Batterie (4 Tests) läuft …")
            report = analyze_export(path)
            st, fx = report["stats"], report["forensics"]
            res.forensik_vorhanden = True
            res.trading_dd_pct = fx["drawdown"]["trading_dd"]["dd_pct"]
            res.trading_dd_usd = fx["drawdown"]["trading_dd"]["dd_usd"]
            res.winrate_pct = st.get("winrate_pct")
            res.max_verlustserie = st.get("max_consecutive_losses")
            res.verlustserie_usd = st.get("max_consecutive_losses_sum")
            expo = fx["exposure"]
            res.peak_positionen = expo.get("peak_open_positions")
            res.peak_netto_lots = expo.get("peak_net_lots")
            res.shock_usd = expo.get("shock_usd")
            res.martingale_flag = fx["martingale"].get("flag")
            res.martingale_evidenz = fx["martingale"].get("evidence") or []
            stops = fx["stops"]
            if stops.get("evidence_level") == 1:
                res.stop_nachweis = (f"Orderbuch: {stops.get('positions_with_sl_tp')}/"
                                     f"{stops.get('positions_total')} mit SL/TP")
            else:
                res.stop_nachweis = stops.get("verdict", "kein Nachweis")[:60]
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
            ev = scoring.evaluate(report, platform=platform)
            res.score = ev["score"]
            res.schranke_verletzt = bool(
                (res.dd_equity_pct or 0) > self.settings.get("schranke_eq_dd_pct", 30.0)
                or ev["schranke_eq_dd_verletzt"])
        except Exception as exc:  # Ein Fehler soll den Lauf nicht abbrechen
            res.fehler = f"{type(exc).__name__}: {exc}"
            log(f"  FEHLER bei {res.id}: {res.fehler}")
            log(traceback.format_exc(limit=3))
        # Alles in die Datenbank (Nutzer-Prinzip: CSV + MQL5-Infos + Befunde)
        try:
            db.init_db()
            db.upsert_signal(res.id, name=res.name, platform=res.platform, url=res.url,
                             autor=res.autor, abo_preis=res.abo_preis_usd,
                             abonnenten=res.abonnenten, wochen=res.wochen,
                             stats={"eq_dd_pct": res.dd_equity_pct,
                                    "bal_dd_pct": res.dd_balance_pct,
                                    "ertrag_monat_pct": res.ertrag_monat_pct,
                                    "pf": res.pf, "growth_pct": res.growth_pct,
                                    "broker_server": res.broker_server})
            if res.trades_path:
                db.store_trade_file(res.id, res.trades_path)
            if res.forensik_vorhanden:
                db.store_forensik(res.id, {
                    "trading_dd": {"pct": res.trading_dd_pct, "usd": res.trading_dd_usd},
                    "winrate_pct": res.winrate_pct,
                    "max_verlustserie": res.max_verlustserie,
                    "verlustserie_usd": res.verlustserie_usd,
                    "peak_exposure": {"positionen": res.peak_positionen,
                                      "netto_lots": res.peak_netto_lots,
                                      "schock_usd": res.shock_usd},
                    "martingale_flag": res.martingale_flag,
                    "stop_nachweis": res.stop_nachweis,
                    "score": res.score, "ampel": res.ampel})
        except Exception as exc:  # DB-Fehler darf den Lauf nicht abbrechen
            log(f"  DB-Hinweis bei {res.id}: {exc}")
        ampel, grund = ampel_for(res, self.settings)
        res.ampel = ampel
        detail = (f" | Score {res.score}, Trading-DD {res.trading_dd_pct} %, "
                  f"Serie {res.max_verlustserie}, Peak {res.peak_positionen} Pos"
                  if res.forensik_vorhanden and res.trading_dd_pct is not None else "")
        res.urteil = grund + detail
        return res

    # ------------------------------------------------------ Schritt 4
    def run_llm(self, results: list[ScanResult], log: LogCb,
                on_progress: ProgressCb | None = None) -> dict:
        """Drei-Stufen-Auswertung (Nutzer-Prinzip):

        Prompt 1  Trade-Analyse   — Strategie ANHAND DER TRADES ermitteln
                                    (starkes Modell, glm-5.3)
        Prompt 2  Risiko-Analyse  — Risikoprofil aus Forensik-Kennzahlen (Flash)
        Prompt 3  Gesamtbericht   — wertet ALLE Teilergebnisse aus, ausfuehrlich
                                    (starkes Modell, glm-5.3)

        Jedes Teilergebnis landet in der Datenbank (Tabelle analyses).
        Fortschritt zählt ausschließlich fertig gespeicherte Prompts. Start-
        und Fehlermeldungen verändern den Zähler nicht. Der Rückgabewert trennt
        erfolgreiche, fehlgeschlagene und nicht ausgeführte Prompts.
        """
        jobs = [r for r in results if r.forensik_vorhanden and not r.fehler]
        total = len(jobs) * 3
        if not self.llm.has_key:
            log("LLM uebersprungen: kein GLM-Key gesetzt (Admin-Bereich).")
            if on_progress:
                on_progress(0, total, "Übersprungen: kein GLM-Key konfiguriert")
            return {"completed": 0, "total": total, "failed": 0,
                    "skipped": total, "reason": "Kein GLM-Key konfiguriert"}
        if not jobs:
            if on_progress:
                on_progress(0, 0, "Übersprungen: keine geeigneten Forensik-Ergebnisse")
            return {"completed": 0, "total": 0, "failed": 0, "skipped": 0,
                    "reason": "Keine geeigneten Forensik-Ergebnisse"}
        kriterien = _kriterien_text(self.settings)
        strong = 2  # starker Modell-Slot (model_stufe2, z. B. glm-5.3)

        def _kandidat(r: ScanResult) -> str:
            return json.dumps({
                "id": r.id, "name": r.name, "platform": r.platform,
                "autor": r.autor, "url": r.url,
                "wochen": r.wochen, "abonnenten": r.abonnenten,
                "abo_preis_usd": r.abo_preis_usd,
                "growth_pct": r.growth_pct, "ertrag_monat_pct": r.ertrag_monat_pct,
                "pf": r.pf, "dd_equity_pct": r.dd_equity_pct,
                "dd_balance_pct": r.dd_balance_pct,
                "broker_server": r.broker_server,
                "score_engine": r.score, "ampel": r.ampel,
                "schranke_verletzt": r.schranke_verletzt,
            }, ensure_ascii=False)

        def _forensik(r: ScanResult) -> str:
            return json.dumps({
                "trading_dd": {"pct": r.trading_dd_pct, "usd": r.trading_dd_usd},
                "winrate_pct": r.winrate_pct,
                "max_verlustserie": r.max_verlustserie,
                "verlustserie_usd": r.verlustserie_usd,
                "peak_exposure": {"positionen": r.peak_positionen,
                                  "netto_lots": r.peak_netto_lots,
                                  "schock_usd": r.shock_usd},
                "martingale_flag": r.martingale_flag,
                "martingale_evidenz": r.martingale_evidenz,
                "stop_nachweis": r.stop_nachweis,
            }, ensure_ascii=False)

        done = 0
        failed = 0

        def _tick(text: str) -> None:
            nonlocal done
            done += 1
            if on_progress:
                on_progress(done, total, text)

        for r in jobs:
            r.llm_fehler = ""
            try:
                # -------- Prompt 1: Trade-Analyse (starkes Modell)
                model_strong = self.settings.get("model_stufe2", "glm-5.3")
                trades_json = "{}"
                n_trades = 0
                if r.trades_path:
                    from .parser import load_export
                    from .trade_data import build_trade_payload
                    payload = build_trade_payload(load_export(r.trades_path))
                    trades_json = json.dumps(payload, ensure_ascii=False)
                    n_trades = payload.get("meta", {}).get("trades", 0)
                prompt = (llm_prompts.load_prompt("trade_analyse")
                          .replace("{kandidat_json}", _kandidat(r))
                          .replace("{trades_json}", trades_json))
                log(f"→ [1/3] Sende Trade-Analyse an {model_strong}: "
                    f"{n_trades} Trades als Engine-Statistik + Beispiel-Trades "
                    f"({len(trades_json):,} Zeichen Daten, Prompt gesamt "
                    f"{len(prompt):,} Zeichen). Modellantwort wird abgewartet …")
                if on_progress:
                    on_progress(done, total, f"Trade-Analyse 1/3: {r.name} · warte auf Modellantwort. Danach: Risiko-Analyse → Gesamtbericht")
                r.trade_analyse = self.llm.chat(prompt, stufe=strong, max_tokens=16384)
                lc = self.llm.last_call
                log(f"  ✓ [1/3] Trade-Analyse fertig: {lc['zeichen']} Zeichen "
                    f"Antwort in {lc['dauer_s']}s (Reasoning "
                    f"{lc['reasoning_tokens']} + Completion "
                    f"{lc['completion_tokens']} Tokens) — gesamt bisher: "
                    f"{self.llm.usage.total_tokens:,} Tokens")
                db.store_analysis(r.id, "trade_analyse",
                                  self.settings.get("model_stufe2", ""),
                                  self.llm.usage.total_tokens, r.trade_analyse)
                _tick(f"Trade-Analyse fertig: {r.name}")

                # -------- Prompt 2: Risiko-Analyse (Flash)
                model_flash = self.settings.get("model_stufe1", "glm-5.3-flash")
                prompt = (llm_prompts.load_prompt("risiko_analyse")
                          .replace("{kandidat_json}", _kandidat(r))
                          .replace("{forensik_json}", _forensik(r))
                          .replace("{kriterien}", kriterien))
                log(f"→ [2/3] Sende Risiko-Analyse an {model_flash}: "
                    f"Forensik-Kennzahlen + Kriterien ({len(prompt):,} "
                    f"Zeichen) …")
                if on_progress:
                    on_progress(done, total, f"Risiko-Analyse 2/3: {r.name} · warte auf Modellantwort. Danach: Gesamtbericht")
                r.risiko_analyse = self.llm.chat(prompt, stufe=1, max_tokens=8192)
                lc = self.llm.last_call
                log(f"  ✓ [2/3] Risiko-Analyse fertig: {lc['zeichen']} Zeichen "
                    f"in {lc['dauer_s']}s — gesamt bisher: "
                    f"{self.llm.usage.total_tokens:,} Tokens")
                db.store_analysis(r.id, "risiko_analyse",
                                  self.settings.get("model_stufe1", ""),
                                  self.llm.usage.total_tokens, r.risiko_analyse)
                _tick(f"Risiko-Analyse fertig: {r.name}")

                # -------- Prompt 3: Gesamtauswertung, ausfuehrlich (starkes Modell)
                prompt = (llm_prompts.load_prompt("gesamtbericht")
                          .replace("{kandidat_json}", _kandidat(r))
                          .replace("{forensik_json}", _forensik(r))
                          .replace("{trade_analyse}", r.trade_analyse or "(nicht erstellt)")
                          .replace("{risiko_analyse}", r.risiko_analyse or "(nicht erstellt)")
                          .replace("{kriterien}", kriterien))
                log(f"→ [3/3] Sende Gesamtauswertung an {model_strong}: ALLE "
                    f"Teilergebnisse zusammen ({len(prompt):,} Zeichen = "
                    f"Forensik + Trade-Analyse {len(r.trade_analyse)} Zeichen + "
                    f"Risiko-Analyse {len(r.risiko_analyse)} Zeichen). Der "
                    f"ausfuehrliche Bericht wird geschrieben; Antwort wird abgewartet …")
                if on_progress:
                    on_progress(done, total, f"Gesamtbericht 3/3: {r.name} · warte auf Modellantwort")
                r.gesamtbericht = self.llm.chat(prompt, stufe=strong, max_tokens=24576)
                lc = self.llm.last_call
                log(f"  ✓ [3/3] Gesamtbericht fertig: {lc['zeichen']} Zeichen in "
                    f"{lc['dauer_s']}s — gesamt bisher: "
                    f"{self.llm.usage.total_tokens:,} Tokens")
                db.store_analysis(r.id, "gesamtbericht",
                                  self.settings.get("model_stufe2", ""),
                                  self.llm.usage.total_tokens, r.gesamtbericht)
                r.kurzfassung = _extract_kurzfassung(r.gesamtbericht)
                log(f"  ● {r.name} abgeschlossen. Kurzfassung: {r.kurzfassung}")
                _tick(f"Gesamtbericht fertig: {r.name}")
            except llm_client.LlmNoBalanceError as exc:
                failed += 1
                r.llm_fehler = str(exc)
                log(f"LLM abgebrochen: {exc}")
                if on_progress:
                    on_progress(done, total, f"Abgebrochen bei {r.name}: {exc}")
                return {"completed": done, "total": total, "failed": failed,
                        "skipped": total - done - failed, "reason": str(exc)}
            except llm_client.LlmError as exc:
                failed += 1
                r.llm_fehler = str(exc)
                log(f"  LLM-Fehler bei {r.name}: {exc}")
                if on_progress:
                    on_progress(done, total, f"Fehler bei {r.name}: {exc}")
        if on_progress:
            on_progress(done, total, f"{done}/{total} Prompts fertig · {failed} fehlgeschlagen")
        return {"completed": done, "total": total, "failed": failed,
                "skipped": total - done - failed,
                "reason": "Einzelne Modellaufrufe fehlgeschlagen" if failed else ""}

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
            except Exception as exc:
                r = ScanResult(id=0, name=path, fehler=f"{type(exc).__name__}: {exc}")
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
                name=path.split("/")[-1].split("\\")[-1].replace("_", " "),
                platform="CSV",
                trades_path=path,
                wochen=st.get("span_weeks"),
                pf=st.get("profit_factor_csv"),
                forensik_vorhanden=True,
                trading_dd_pct=fx["drawdown"]["trading_dd"]["dd_pct"],
                trading_dd_usd=fx["drawdown"]["trading_dd"]["dd_usd"],
                winrate_pct=st.get("winrate_pct"),
                max_verlustserie=st.get("max_consecutive_losses"),
                verlustserie_usd=st.get("max_consecutive_losses_sum"),
                peak_positionen=fx["exposure"].get("peak_open_positions"),
                peak_netto_lots=fx["exposure"].get("peak_net_lots"),
                shock_usd=fx["exposure"].get("shock_usd"),
                martingale_flag=fx["martingale"].get("flag"),
                martingale_evidenz=fx["martingale"].get("evidence") or [],
            )
            stops = fx["stops"]
            r.stop_nachweis = (f"Orderbuch: {stops.get('positions_with_sl_tp')}/"
                               f"{stops.get('positions_total')} mit SL/TP"
                               if stops.get("evidence_level") == 1
                               else stops.get("verdict", "kein Nachweis"))
            ev = scoring.evaluate(report)
            r.score = ev["score"]
            r.schranke_verletzt = ev["schranke_eq_dd_verletzt"]
            if sid in meta:
                r.name = meta[sid].get("name", r.name)
                r.score = meta[sid].get("score", r.score)
                r.abo_preis_usd = meta[sid].get("abo_preis_usd")
                r.ertrag_monat_pct = meta[sid].get("monat_pct")
            r.ampel, grund = ampel_for(r, settings)
            r.urteil = grund + (f" | Score {r.score}, Trading-DD {r.trading_dd_pct} %"
                                if r.trading_dd_pct is not None else "")
            # Fruehere LLM-Analysen aus der DB nachladen (Nutzer-Prinzip:
            # Berichte bleiben Datenbank-uebergreifend erhalten)
            try:
                db.init_db()
                db.upsert_signal(r.id, name=r.name, platform=r.platform,
                                 url=r.url or f"https://www.mql5.com/en/signals/{r.id}",
                                 abo_preis=r.abo_preis_usd, wochen=r.wochen,
                                 stats={"trading_dd_pct": r.trading_dd_pct,
                                        "winrate_pct": r.winrate_pct, "score": r.score})
                db.store_trade_file(r.id, path)
                db.store_forensik(r.id, {"score": r.score, "ampel": r.ampel,
                                         "trading_dd_pct": r.trading_dd_pct})
                for kind, attr in (("trade_analyse", "trade_analyse"),
                                   ("risiko_analyse", "risiko_analyse"),
                                   ("gesamtbericht", "gesamtbericht")):
                    prev = db.get_latest_analysis(r.id, kind)
                    if prev:
                        setattr(r, attr, prev["text"])
                if r.gesamtbericht and not r.kurzfassung:
                    r.kurzfassung = _extract_kurzfassung(r.gesamtbericht)
            except Exception:
                pass
            results.append(r)
        return results

    @staticmethod
    def save_run(results: list[ScanResult], logs: dict[str, list[str]]) -> str:
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        run_dir = config.RUNS_DIR / stamp
        run_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "zeitstempel": stamp,
            "ergebnisse": [vars(r) for r in results],
            "logs": logs,
        }
        out = run_dir / "results.json"
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                       encoding="utf-8")
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
