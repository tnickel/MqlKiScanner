"""Three report stages with independent model/storage outcomes per prompt."""
from __future__ import annotations

import csv
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import config, db
from .llm import client as llm_client
from .llm import prompt_fill
from .parser import load_export
from .trade_data import build_trade_payload


def run_llm(pipe, results, log, on_progress=None, should_stop=None) -> dict:
    # Pipeline owns the report contract; import after its module is initialized.
    from .pipeline import (
        _extract_kurzfassung, _kriterien_text,
        refresh_report_verdict, report_basis_for,
    )

    jobs = [r for r in results
            if r.source_kind == "live" and r.forensik_vorhanden and not r.fehler]
    total = len(jobs) * 3
    done = failed = 0
    current_signal = 0
    updated_ids: list[int] = []

    def mark_updated(result):
        if result.id not in updated_ids:
            updated_ids.append(result.id)

    def progress(message):
        if on_progress:
            prefix = f"Signal {current_signal}/{len(jobs)} · " if current_signal else ""
            on_progress(done, total, prefix + message)

    def summary(reason=""):
        return {"completed": done, "total": total, "failed": failed,
                "skipped": total - done - failed, "reason": reason,
                "updated_ids": list(updated_ids)}

    def stopped():
        log("Stop angefordert — verbleibende Prompts werden nicht mehr gesendet.")
        progress("Abgebrochen: Stop-Anforderung")
        return summary("Abbruch per Stop-Button")

    if not pipe.llm.has_key:
        log("LLM uebersprungen: kein GLM-Key gesetzt (Admin-Bereich).")
        progress("Übersprungen: kein GLM-Key konfiguriert")
        return summary("Kein GLM-Key konfiguriert")
    if not jobs:
        progress("Übersprungen: keine geeigneten Forensik-Ergebnisse")
        return summary("Keine geeigneten Forensik-Ergebnisse")

    kriterien = _kriterien_text(pipe.settings)
    for current_signal, result in enumerate(jobs, 1):
        if should_stop and should_stop():
            return stopped()
        result.llm_fehler = ""
        errors = []

        def record_failure(exc, label):
            nonlocal failed
            failed += 1
            errors.append(str(exc))
            result.llm_fehler = "; ".join(errors)
            log(f"  {label} bei {result.name}: {exc}")
            progress(f"Fehler bei {result.name}: {exc}")

        try:
            refresh_report_verdict(result, pipe.settings)
            basis = report_basis_for(result, pipe.settings)
            if not basis or getattr(result, "berichte_basis", "") != basis:
                had_reports = any(getattr(result, field, "") for field in
                                  ("trade_analyse", "risiko_analyse", "gesamtbericht"))
                for field in ("trade_analyse", "risiko_analyse", "gesamtbericht", "kurzfassung"):
                    setattr(result, field, "")
                result.gesamtbericht_at = ""
                result.berichte_basis = ""
                if had_reports:
                    result.bericht_hinweis = "Bisherige Berichte passen nicht zur aktuellen Bewertungsbasis."
            if not basis:
                message = "Keine belegte aktuelle Bewertungsbasis für KI-Berichte."
                if result.trades_path:
                    message = "Trade-Export nicht lesbar: " + message
                raise llm_client.LlmError(message)
            trades_json = "{}"
            n_trades = 0
            if result.trades_path:
                try:
                    payload = build_trade_payload(load_export(result.trades_path))
                except (OSError, ValueError, csv.Error) as exc:
                    raise llm_client.LlmError(
                        f"Trade-Export nicht lesbar: {type(exc).__name__}: {exc}") from exc
                trades_json = json.dumps(payload, ensure_ascii=False)
                n_trades = payload.get("meta", {}).get("trades", 0)
            model_strong = pipe.settings.get("model_stufe2", "glm-5.3")
            model_flash = pipe.settings.get("model_stufe1", "glm-5.3-flash")
            trade_prompt = prompt_fill.build_trade_prompt(result, trades_json)
            risk_prompt = prompt_fill.build_risk_prompt(result, kriterien)
        except Exception as exc:
            record_failure(exc, "Berichtsvorbereitung fehlgeschlagen")
            if isinstance(exc, (llm_client.LlmNoBalanceError, llm_client.LlmBudgetError)):
                return summary(str(exc))
            continue

        log(f"→ [1+2/3] Parallel: Trade-Analyse ({model_strong}, {n_trades} Trades) + "
            f"Risiko-Analyse ({model_flash}) für {result.name} …")
        progress(f"Trade- + Risiko-Analyse parallel: {result.name} · warte auf Modellantworten. "
                 "Danach: Gesamtbericht")
        stages = [
            ("trade_analyse", "Trade-Analyse", trade_prompt, 2, 16384, model_strong),
            ("risiko_analyse", "Risiko-Analyse", risk_prompt, 1, 8192, model_flash),
        ]
        outcomes = []
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [(stage, pool.submit(pipe.llm.chat, stage[2], stufe=stage[3],
                                          max_tokens=stage[4], meta_out={})) for stage in stages]
            for stage, future in futures:
                try:
                    outcomes.append((stage, future.result(), None))
                except Exception as exc:
                    outcomes.append((stage, None, exc))

        # Preserve BOTH paid-for responses before storage can fail on either.
        for stage, text, exc in outcomes:
            if exc is None:
                setattr(result, stage[0], text)
                setattr(result, f"{stage[0]}_model", stage[5])
                result.berichte_basis = basis
                result.bericht_hinweis = ""

        abort_error = None
        for stage, text, exc in outcomes:
            field, label, _, _, _, model = stage
            if exc is not None:
                record_failure(exc, f"{label} fehlgeschlagen")
                if isinstance(exc, (llm_client.LlmNoBalanceError, llm_client.LlmBudgetError)):
                    abort_error = abort_error or exc
                continue
            try:
                created_at = db.store_analysis(
                    result.id, field, model, pipe.llm.usage.total_tokens, text, basis=basis)
            except Exception as storage_error:
                record_failure(RuntimeError(f"{label} nicht gespeichert: {storage_error}"),
                               "Speicherfehler")
            else:
                setattr(result, f"{field}_at", created_at)
                done += 1
                mark_updated(result)
                log(f"  ✓ {label} gespeichert: {result.name}")
                progress(f"{label} fertig: {result.name}")
        if abort_error:
            log(f"LLM abgebrochen: {abort_error}")
            progress(f"Abgebrochen bei {result.name}: {abort_error}")
            return summary(str(abort_error))
        if errors:
            # No synthesis from missing or unsuccessfully persisted parts.
            continue
        if should_stop and should_stop():
            return stopped()

        try:
            prompt = prompt_fill.build_gesamtbericht_prompt(
                result, kriterien, result.trade_analyse, result.risiko_analyse)
            log(f"→ [3/3] Gesamtbericht für {result.name}: {len(prompt):,} Zeichen …")
            progress(f"Gesamtbericht 3/3: {result.name} · warte auf Modellantwort")
            result.gesamtbericht = pipe.llm.chat(prompt, stufe=2, max_tokens=24576, meta_out={})
            result.gesamtbericht_at = datetime.now().isoformat(sep=" ", timespec="seconds")
            result.gesamtbericht_model = model_strong
            result.kurzfassung = _extract_kurzfassung(result.gesamtbericht)
            result.berichte_basis = basis
        except Exception as exc:
            record_failure(exc, "Gesamtbericht fehlgeschlagen")
            if isinstance(exc, (llm_client.LlmNoBalanceError, llm_client.LlmBudgetError)):
                progress(f"Abgebrochen bei {result.name}: {exc}")
                return summary(str(exc))
            continue
        try:
            result.gesamtbericht_at = db.store_analysis(
                result.id, "gesamtbericht", model_strong,
                pipe.llm.usage.total_tokens, result.gesamtbericht, basis=basis)
        except Exception as exc:
            record_failure(RuntimeError(f"Gesamtbericht nicht gespeichert: {exc}"), "Speicherfehler")
        else:
            done += 1
            mark_updated(result)
            log(f"  ● {result.name} abgeschlossen. Kurzfassung: {result.kurzfassung}")
            progress(f"Gesamtbericht fertig: {result.name}")

    progress(f"{done}/{total} Prompts fertig · {failed} fehlgeschlagen")
    return summary("Einzelne Modellaufrufe oder Speicherungen fehlgeschlagen" if failed else "")


def run_tiefenanalyse_einzeln(result, settings: dict | None = None, log=None) -> dict:
    """Erweiterte KI-Analyse (Prompt 5) für EIN Signal — manuell gestartet.

    Anders als die Workflow-Berichte läuft diese Analyse NICHT im Lauf,
    sondern per Button in der Signal-Detailansicht. Starkes Modell
    (Stufe 2) und die vollständigen Trade-Daten im Prompt, weil die
    Aufgabe die Auswertung der Trades selbst verlangt. Ergebnis landet
    als kind='tiefenanalyse' in der Datenbank und am Ergebnis-Objekt
    (dort erzeugt der PDF-Mechanismus wie üblich das Dokument).
    """
    from .pipeline import report_basis_for  # später Import: kein Kreisimport

    settings = {**config.load_settings(), **(settings or {})}
    if not getattr(result, "trades_path", ""):
        raise llm_client.LlmError(
            "Keine Trade-Daten zu diesem Signal — die Erweiterte KI-Analyse "
            "wertet die Tradeliste aus und braucht den Export.")
    client = llm_client.GlmClient(
        model_stufe1=settings.get("model_stufe1", config.MODEL_STUFE1),
        model_stufe2=settings.get("model_stufe2", config.MODEL_STUFE2),
        max_total_tokens=int(settings.get("llm_max_total_tokens", 5_000_000)),
        base_url=settings.get("glm_base_url") or None,
        # Tiefenanalyse-Prompts sind gross (Tradedaten) und die Antworten lang -
        # gemessen ~64 Tokens/s: bis zu 131.072 Ausgabe-Tokens brauchen im
        # Extremfall ~30+ Minuten, der Client-Default von 300 s wuerde den
        # Aufruf vorzeitig abbrechen (Nutzer: Faktor 2, laengere Phasen ok).
        timeout=2400,
    )
    if not client.has_key:
        raise llm_client.LlmError(
            "Kein GLM-Key gesetzt (Admin-Bereich → Zugänge). "
            "Die Erweiterte KI-Analyse ist optional.")
    try:
        payload = build_trade_payload(load_export(result.trades_path))
    except (OSError, ValueError, csv.Error) as exc:
        raise llm_client.LlmError(
            f"Trade-Export nicht lesbar: {type(exc).__name__}: {exc}") from exc
    trades_json = json.dumps(payload, ensure_ascii=False)
    if log:
        log(f"Trade-Daten geladen ({payload.get('meta', {}).get('trades', 0)} Trades) — "
            "Tiefenanalyse-Prompt wird gebaut …")
    prompt = prompt_fill.build_tiefenanalyse_prompt(result, trades_json)
    if log:
        log(f"Modellaufruf Stufe 2 gestartet ({len(prompt):,} Zeichen Prompt) — "
            "dauert einige Minuten, bei langen Antworten auch 15–30 Minuten.")
    # Ausgabelimit bewusst grosszuegig (Nutzer-Vorgabe: Faktor 2, "wir haben
    # genug Tokens"): glm-5.3 bezahlt Reasoning-Tokens aus demselben Budget -
    # bei 24.576 brach die Antwort wiederholt mitten drin ab (finish_reason=
    # length, ~64 Tokens/s gemessen). Zeitlimit proportional (Faktor 2).
    text = client.chat(prompt, stufe=2, max_tokens=131072, meta_out={})
    model = settings.get("model_stufe2", config.MODEL_STUFE2)
    try:
        basis = report_basis_for(result, settings)
    except Exception:
        basis = None
    created_at = db.store_analysis(result.id, "tiefenanalyse", model,
                                   client.usage.total_tokens, text, basis=basis)
    result.tiefenanalyse = text
    result.tiefenanalyse_at = created_at
    result.tiefenanalyse_model = model
    if log:
        log("Erweiterte KI-Analyse gespeichert (Datenbank + PDF-Basis).")
    return {"text": text, "model": model, "created_at": created_at}
