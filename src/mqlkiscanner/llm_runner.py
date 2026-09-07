"""Three report stages with independent model/storage outcomes per prompt."""
from __future__ import annotations

import csv
import json
from concurrent.futures import ThreadPoolExecutor

from . import db
from .llm import client as llm_client, prompts as llm_prompts
from .parser import load_export
from .trade_data import build_trade_payload


def run_llm(pipe, results, log, on_progress=None, should_stop=None) -> dict:
    # Pipeline owns the report contract; import after its module is initialized.
    from .pipeline import (
        _extract_kurzfassung, _forensik_json, _kandidat_json, _kriterien_text,
        refresh_report_verdict, report_basis_for,
    )

    jobs = [r for r in results
            if r.source_kind == "live" and r.forensik_vorhanden and not r.fehler]
    total = len(jobs) * 3
    done = failed = 0
    updated_ids: list[int] = []

    def mark_updated(result):
        if result.id not in updated_ids:
            updated_ids.append(result.id)

    def progress(message):
        if on_progress:
            on_progress(done, total, message)

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
    for result in jobs:
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
            trade_prompt = (llm_prompts.load_prompt("trade_analyse")
                            .replace("{kandidat_json}", _kandidat_json(result))
                            .replace("{trades_json}", trades_json))
            risk_prompt = (llm_prompts.load_prompt("risiko_analyse")
                           .replace("{kandidat_json}", _kandidat_json(result))
                           .replace("{forensik_json}", _forensik_json(result))
                           .replace("{kriterien}", kriterien))
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
                db.store_analysis(result.id, field, model, pipe.llm.usage.total_tokens, text,
                                  basis=basis)
            except Exception as storage_error:
                record_failure(RuntimeError(f"{label} nicht gespeichert: {storage_error}"),
                               "Speicherfehler")
            else:
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
            prompt = (llm_prompts.load_prompt("gesamtbericht")
                      .replace("{kandidat_json}", _kandidat_json(result))
                      .replace("{forensik_json}", _forensik_json(result))
                      .replace("{trade_analyse}", result.trade_analyse)
                      .replace("{risiko_analyse}", result.risiko_analyse)
                      .replace("{kriterien}", kriterien))
            log(f"→ [3/3] Gesamtbericht für {result.name}: {len(prompt):,} Zeichen …")
            progress(f"Gesamtbericht 3/3: {result.name} · warte auf Modellantwort")
            result.gesamtbericht = pipe.llm.chat(prompt, stufe=2, max_tokens=24576, meta_out={})
            result.kurzfassung = _extract_kurzfassung(result.gesamtbericht)
            result.berichte_basis = basis
        except Exception as exc:
            record_failure(exc, "Gesamtbericht fehlgeschlagen")
            if isinstance(exc, (llm_client.LlmNoBalanceError, llm_client.LlmBudgetError)):
                progress(f"Abgebrochen bei {result.name}: {exc}")
                return summary(str(exc))
            continue
        try:
            db.store_analysis(result.id, "gesamtbericht", model_strong,
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
