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
    stufe1_profil: str = ""
    stufe2_verdict: str = ""
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
            "Urteil": self.urteil, "Fehler": self.fehler,
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
            stats = signal_stats.fetch_signal_stats(session, res.id)
            res.dd_equity_pct = stats.get("dd_equity_pct")
            res.dd_balance_pct = stats.get("dd_balance_pct")
            res.ertrag_monat_pct = stats.get("monthly_growth_pct")
            res.pf = stats.get("profit_factor")
            if res.wochen is None:
                res.wochen = stats.get("weeks")
            res.broker_server = stats.get("broker_server")
            log(f"  Stats: EQ-DD {res.dd_equity_pct} % | Bal-DD {res.dd_balance_pct} % | "
                f"PF {res.pf} | Ertrag {res.ertrag_monat_pct} %/Monat")

            path, from_cache = exporter.export_positions(
                session, res.id,
                extra_pause_s=float(self.settings.get("rate_pause_zwischen_signalen_s", 5.0)))
            log(f"  Trade-Export: {path} {'(Cache)' if from_cache else '(neu geladen)'}")
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
        ampel, grund = ampel_for(res, self.settings)
        res.ampel = ampel
        detail = (f" | Score {res.score}, Trading-DD {res.trading_dd_pct} %, "
                  f"Serie {res.max_verlustserie}, Peak {res.peak_positionen} Pos"
                  if res.forensik_vorhanden and res.trading_dd_pct is not None else "")
        res.urteil = grund + detail
        return res

    # ------------------------------------------------------ Schritt 4
    def run_llm(self, results: list[ScanResult], log: LogCb,
                on_progress: ProgressCb | None = None) -> None:
        """Stufe 1 (Flash) fuer alle mit Forensik; Stufe 2 (stark) fuer Finalisten."""
        if not self.llm.has_key:
            log("LLM uebersprungen: kein GLM-Key gesetzt (Admin-Bereich).")
            return
        kriterien = _kriterien_text(self.settings)
        finalists: list[ScanResult] = []
        stage1_jobs = [r for r in results if r.forensik_vorhanden and not r.fehler]

        jobs = [(1, r) for r in stage1_jobs]
        if self.settings.get("llm_stufe2", True):
            jobs += [(2, r) for r in stage1_jobs
                     if r.ampel == "🟢" or (r.score is not None and r.score < 5.0)]
        finalists = [r for stufe, r in jobs if stufe == 2]

        for i, (stufe, r) in enumerate(jobs):
            if on_progress:
                on_progress(i, len(jobs),
                            f"Stufe {stufe}: {r.name} ({len(jobs) - i} verbleibend)")
            cand_json = json.dumps({
                "id": r.id, "name": r.name, "platform": r.platform,
                "wochen": r.wochen, "abonnenten": r.abonnenten,
                "growth_pct": r.growth_pct, "ertrag_monat_pct": r.ertrag_monat_pct,
                "pf": r.pf, "dd_equity_pct": r.dd_equity_pct,
                "dd_balance_pct": r.dd_balance_pct, "score_engine": r.score,
                "schranke_verletzt": r.schranke_verletzt,
            }, ensure_ascii=False)
            forensik_json = json.dumps({
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
            try:
                if stufe == 1 and self.settings.get("llm_stufe1", True):
                    prompt = (llm_prompts.load_prompt("stufe1_profil")
                              .replace("{kandidat_json}", cand_json)
                              .replace("{forensik_json}", forensik_json)
                              .replace("{kriterien}", kriterien))
                    r.stufe1_profil = self.llm.chat(prompt, stufe=1, max_tokens=1200)
                    log(f"  [Stufe 1] {r.name}: Profil ({self.llm.usage.total_tokens} Tokens gesamt)")
                elif stufe == 2 and self.settings.get("llm_stufe2", True):
                    prompt = (llm_prompts.load_prompt("stufe2_verdict")
                              .replace("{kandidat_json}", cand_json)
                              .replace("{forensik_json}", forensik_json)
                              .replace("{stufe1_profil}", r.stufe1_profil or "(kein Profil)")
                              .replace("{kriterien}", kriterien))
                    r.stufe2_verdict = self.llm.chat(prompt, stufe=2, max_tokens=1500)
                    log(f"  [Stufe 2] {r.name}: Verdict ({self.llm.usage.total_tokens} Tokens gesamt)")
            except llm_client.LlmNoBalanceError as exc:
                for rr in jobs[i:]:
                    rr[1].llm_fehler = str(exc)
                log(f"LLM abgebrochen: {exc}")
                return
            except llm_client.LlmError as exc:
                r.llm_fehler = str(exc)
                log(f"  LLM-Fehler bei {r.name}: {exc}")
            if on_progress:
                on_progress(i + 1, len(jobs), f"{len(finalists)} Finalisten bewertet")

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
