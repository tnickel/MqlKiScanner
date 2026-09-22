# -*- coding: utf-8 -*-
"""Profil-Destillation: Tiefenanalyse + Gesamtbericht → Algo-Profil (Phase B).

Einmalig je Signal (und nach einer erneuerten Tiefenanalyse): Das starkes
Modell destilliert das dokumentierte Handelsprofil inklusive nummerierter
Konformitäts- und Warn-Merkmale — der Messvorschrift, an der der Betreuer
später die Tages-Deltas prüft. Das Profil ist versioniert; jede Änderung
mit Begründung. Es ist Beobachtungsbasis — nie Bewertungsgrundlage.

Ohne Belege (weder Tiefenanalyse noch Gesamtbericht) wird KEIN Profil
erfunden, sondern der Mangel protokolliert — Grundlage fehlt heißt:
Betreuer kann für dieses Signal nicht prüfen.
"""
from __future__ import annotations

import json

from .. import config, db
from ..llm import client as llm_client
from . import dossier, journal, rollen, rollen_prompts


def grundlagen_lesen(signal_id: int) -> dict:
    """Neueste Tiefenanalyse/Gesamtbericht/Forensik aus der DB (Texte)."""
    tiefen = db.get_latest_analysis(signal_id, "tiefenanalyse") or {}
    bericht = db.get_latest_analysis(signal_id, "gesamtbericht") or {}
    with db._connect() as conn:
        forensik = conn.execute("SELECT json FROM forensik WHERE signal_id=?",
                                (signal_id,)).fetchone()
    return {
        "tiefenanalyse": (tiefen.get("text") or "").strip(),
        "tiefenanalyse_at": tiefen.get("created_at") or "",
        "gesamtbericht": (bericht.get("text") or "").strip(),
        "gesamtbericht_at": bericht.get("created_at") or "",
        "forensik_json": (forensik["json"] if forensik else "") or "",
    }


def profil_erstellen(signal_id: int, signal_name: str, signal_url: str,
                     settings: dict | None = None, *,
                     lauf_id: int | None = None, log=print) -> dict:
    """Ein Profil destillieren (überspringt vorhandene; False ohne Grundlage).

    Rückgabe: {"erstellt": bool, "grund": str, "version": int|None}.
    """
    settings = settings if settings is not None else config.load_settings()
    modell = settings.get("agenten_betreuer_modell", rollen.STANDARD_MODELL)
    max_tokens = int(settings.get("agenten_betreuer_max_tokens", 8192))
    if dossier.profil_lesen(signal_id):
        return {"erstellt": False, "grund": "Profil vorhanden.",
                "version": None}
    basis = grundlagen_lesen(signal_id)
    if not basis["tiefenanalyse"] and not basis["gesamtbericht"]:
        grund = ("Weder Tiefenanalyse noch Gesamtbericht vorhanden — "
                 "kein Profil ohne Belegbasis (nichts erfunden).")
        if lauf_id:
            journal.schritt_protokollieren(
                lauf_id, "betreuer", "profil_destillation", status="skipped",
                detail={"grund": grund, "signal": signal_name})
        return {"erstellt": False, "grund": grund, "version": None}

    budget_rest = max(0, int(settings.get("agenten_tagesbudget_tokens",
                                          500_000)) - journal.tokens_heute())
    client = llm_client.GlmClient(
        model_stufe1=settings.get("model_stufe1", config.MODEL_STUFE1),
        model_stufe2=settings.get("model_stufe2", config.MODEL_STUFE2),
        max_total_tokens=budget_rest or 1,
        base_url=settings.get("glm_base_url") or None,
        timeout=2400,  # große Prompts (Tiefenanalyse), glm-5.3 antwortet langsam
    )
    if not client.has_key:
        grund = "Kein GLM-Key gesetzt — Destillation verschoben."
        if lauf_id:
            journal.schritt_protokollieren(
                lauf_id, "betreuer", "profil_destillation", status="skipped",
                detail={"grund": grund, "signal": signal_name})
        return {"erstellt": False, "grund": grund, "version": None}
    if budget_rest <= 0:
        grund = "Tagesbudget erschöpft — Destillation verschoben."
        if lauf_id:
            journal.schritt_protokollieren(
                lauf_id, "betreuer", "profil_destillation", status="skipped",
                detail={"grund": grund, "signal": signal_name})
        return {"erstellt": False, "grund": grund, "version": None}

    prompt = rollen_prompts.fuellung(
        rollen_prompts.lade_vorlage("profil_destillation"),
        {"signal_name": signal_name, "signal_url": signal_url,
         "tiefenanalyse": basis["tiefenanalyse"] or "(nicht vorhanden)",
         "gesamtbericht": basis["gesamtbericht"] or "(nicht vorhanden)",
         "forensik_json": basis["forensik_json"] or "(keine Forensik)"})
    meta: dict = {}
    import time as _time
    beginn = _time.monotonic()
    try:
        antwort = client.chat(prompt, model=modell, stufe=2,
                              max_tokens=max_tokens, meta_out=meta)
    except llm_client.LlmError as exc:
        if lauf_id:
            journal.schritt_protokollieren(
                lauf_id, "betreuer", "profil_destillation", status="fehler",
                prompt=prompt, modell=modell,
                tokens=client.usage.total_tokens,
                dauer_s=round(_time.monotonic() - beginn, 1),
                detail={"fehler": str(exc), "signal": signal_name})
        log(f"  Destillation {signal_name} fehlgeschlagen: {exc}")
        return {"erstellt": False, "grund": str(exc), "version": None}

    grundlage = {"tiefenanalyse_vom": basis["tiefenanalyse_at"],
                 "gesamtbericht_vom": basis["gesamtbericht_at"]}
    version = dossier.profil_speichern(
        signal_id, antwort, modell, grundlage,
        aenderungs_grund="Erststellung aus Tiefenanalyse/Gesamtbericht")
    if lauf_id:
        journal.schritt_protokollieren(
            lauf_id, "betreuer", "profil_destillation", prompt=prompt,
            antwort=antwort, modell=modell,
            tokens=meta.get("total_tokens", client.usage.total_tokens) or 0,
            dauer_s=meta.get("dauer_s"),
            detail={"signal": signal_name, "version": version,
                    "grundlage": grundlage})
    log(f"  Profil {signal_name} destilliert (Version {version}).")
    return {"erstellt": True, "grund": "destilliert", "version": version}
