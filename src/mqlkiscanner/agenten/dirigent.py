# -*- coding: utf-8 -*-
"""Dirigent — der Tageslauf (Phase A des Agentenbetriebs, doc/19 §4.1).

Der Dirigent ist überwiegend deterministischer Code: Er sammelt den
Lagestatus, leitet daraus den Tagesplan ab und protokolliert jeden
Schritt. Das LLM entscheidet nur Randfragen — seine Antwort wird auf die
Aktions-Whitelist gefiltert und NICHT blind ausgeführt (Nutzer-Regel:
Whitelist statt Freiheit). Läuft ohne Key komplett ohne Modellaufruf.

Phase A: Der Tageslauf plant und protokolliert nur; das Anstoßen echter
Scans folgt in Phase E. Damit ist das Abnahmekriterium erfüllt: Ein
Dirigent-Tageslauf ist im Protokoll vollständig nachlesbar.
"""
from __future__ import annotations

import json
from datetime import datetime

from .. import config, db
from ..llm import client as llm_client
from . import journal, lock, rollen, rollen_prompts

# Erlaubte Aktionen der LLM-Entscheidung (doc/19, Anhang A.1).
ERLAUBTE_AKTIONEN = frozenset((
    "delta_laufen_lassen", "delta_ueberspringen", "markt_holen",
    "markt_ueberspringen", "scan_gelb_gruen", "scan_full", "meldung_schicken",
))


def _lagestatus(settings: dict) -> dict:
    """Deterministische Ist-Aufnahme — alles, was der Plan braucht."""
    journal.init_journal()
    von_heute = [l for l in journal.list_laeufe(limit=50)
                 if l["start"].startswith(datetime.now().strftime("%Y-%m-%d"))]
    return {
        "jetzt": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "wochentag": datetime.now().strftime("%A"),
        "wochenende": datetime.now().weekday() >= 5,
        "start_zeit": settings.get("agenten_start_zeit", "06:30"),
        "tagesbudget_tokens": int(settings.get("agenten_tagesbudget_tokens",
                                               500_000)),
        "monatsbudget_tokens": int(settings.get("agenten_monatsbudget_tokens",
                                                5_000_000)),
        "tokens_heute": journal.tokens_heute(),
        "tokens_monat": journal.tokens_monat(),
        "laeufe_heute": len(von_heute),
        "glm_key_vorhanden": bool(llm_client.GlmClient(
            model_stufe1="x", model_stufe2="x").has_key),
        "rollen_aktiv": [r.key for r in rollen.ROLLEN
                         if settings.get(f"agenten_{r.key}_aktiv", True)],
    }


def _tagesplan(lage: dict) -> list[str]:
    """Der Code-Plan — deterministisch, ohne Modell.

    Phase A: nur Beobachten und Protokollieren. Wochenende ruht
    (Forex geschlossen), Budget-Erschöpfung pausiert Modellaufrufe.
    """
    if lage["wochenende"]:
        return ["ruhen_markt_geschlossen"]
    if lage["tokens_heute"] >= lage["tagesbudget_tokens"]:
        return ["budget_pause"]
    if lage["tokens_monat"] >= lage["monatsbudget_tokens"]:
        return ["budget_pause"]
    return ["protokoll_und_journal"]


def _llm_entscheidung(lage: dict, settings: dict, lauf_id: int,
                      log) -> dict | None:
    """Optionale LLM-Randentscheidung — whitelistegefiltert, voll protokolliert."""
    if not settings.get("agenten_dirigent_llm", True):
        return None
    modell = settings.get("agenten_dirigent_modell", rollen.STANDARD_MODELL)
    max_tokens = int(settings.get("agenten_dirigent_max_tokens", 2048))
    budget_rest = max(0, lage["tagesbudget_tokens"] - lage["tokens_heute"])
    client = llm_client.GlmClient(
        model_stufe1=settings.get("model_stufe1", config.MODEL_STUFE1),
        model_stufe2=settings.get("model_stufe2", config.MODEL_STUFE2),
        max_total_tokens=budget_rest or 1,
        base_url=settings.get("glm_base_url") or None,
    )
    if not client.has_key:
        journal.schritt_protokollieren(
            lauf_id, "dirigent", "llm_entscheidung", status="skipped",
            detail={"grund": "Kein GLM-Key gesetzt — LLM-Entscheidung entfällt.",
                    "modell": modell})
        return None
    if budget_rest <= 0:
        journal.schritt_protokollieren(
            lauf_id, "dirigent", "llm_entscheidung", status="skipped",
            detail={"grund": "Tagesbudget erschöpft.", "modell": modell})
        return None
    zeitplan = {"phase": "A", "takt_dirigent": lage["start_zeit"],
                "erkennte": "Phase A: nur Planung und Protokoll"}
    prompt = rollen_prompts.fuellung(
        rollen_prompts.lade_vorlage("dirigent_planung"),
        {"lagestatus_json": json.dumps(lage, ensure_ascii=False, indent=2),
         "zeitplan_json": json.dumps(zeitplan, ensure_ascii=False)})
    meta: dict = {}
    import time as _time
    beginn = _time.monotonic()
    try:
        antwort = client.chat(prompt, model=modell, stufe=2,
                              max_tokens=max_tokens, meta_out=meta)
    except llm_client.LlmError as exc:
        journal.schritt_protokollieren(
            lauf_id, "dirigent", "llm_entscheidung", status="fehler",
            prompt=prompt, modell=modell, tokens=client.usage.total_tokens,
            dauer_s=round(_time.monotonic() - beginn, 1),
            detail={"fehler": str(exc)})
        log(f"  Dirigent-LLM-Entscheidung fehlgeschlagen: {exc}")
        return None
    entscheidung = _whitelist_filter(antwort)
    journal.schritt_protokollieren(
        lauf_id, "dirigent", "llm_entscheidung", prompt=prompt, antwort=antwort,
        modell=modell, tokens=meta.get("total_tokens",
                                       client.usage.total_tokens) or 0,
        dauer_s=meta.get("dauer_s", round(_time.monotonic() - beginn, 1)),
        detail={"filter": entscheidung})
    return entscheidung


def _whitelist_filter(antwort: str) -> dict:
    """Nur bekannte Aktionen übernehmen; alles andere wird verworfen."""
    try:
        roh = json.loads(antwort[antwort.index("{"):antwort.rindex("}") + 1])
    except (ValueError, IndexError):
        return {"aktionen": [], "begruendung": "Antwort war kein JSON — verworfen."}
    aktionen = [a for a in (roh.get("aktionen") or [])
                if isinstance(a, str) and a in ERLAUBTE_AKTIONEN]
    return {"aktionen": aktionen,
            "begruendung": str(roh.get("begruendung") or "")[:300]}


def tageslauf(quelle: str = "daemon", log=print) -> dict:
    """Ein vollständiger Dirigent-Tageslauf — gibt die Zusammenfassung zurück.

    Ablauf: Lock prüfen → Lauf öffnen → Lagestatus-Schritt → Code-Plan →
    (optional) LLM-Entscheidung → Lauf abschließen. Jeder Schritt steht im
    Protokoll; der LLM-Schritt mit vollständigem Prompt und vollständiger
    Antwort (kein Trockenmodus — Nutzer-Entscheidung 22.09.2026).
    """
    settings = config.load_settings()
    journal.init_journal()
    try:
        with lock.lauf_lock(config.DATA_DIR):
            lauf_id = journal.lauf_starten("dirigent", quelle=quelle)
    except lock.LockBesetzt as exc:
        lauf_id = journal.lauf_starten("dirigent", quelle=quelle)
        journal.schritt_protokollieren(
            lauf_id, "dirigent", "lock", status="skipped",
            detail={"grund": str(exc)})
        journal.lauf_abschliessen(lauf_id, "skipped", f"Lauf-Lock belegt: {exc}")
        log(f"Dirigent übersprungen: {exc}")
        return {"status": "skipped", "grund": str(exc), "lauf_id": lauf_id}

    journal.schritt_protokollieren(lauf_id, "dirigent", "lock", status="ok",
                                   detail={"inhaber_pid": "self"})
    lage = _lagestatus(settings)
    journal.schritt_protokollieren(lauf_id, "dirigent", "lagestatus",
                                   detail=lage)
    plan = _tagesplan(lage)
    journal.schritt_protokollieren(lauf_id, "dirigent", "tagesplan",
                                   detail={"aktionen": plan})
    entscheidung = _llm_entscheidung(lage, settings, lauf_id, log)
    if entscheidung and entscheidung["aktionen"]:
        journal.schritt_protokollieren(
            lauf_id, "dirigent", "entscheidung",
            detail={"uebernommene_aktionen": entscheidung["aktionen"],
                    "begruendung": entscheidung["begruendung"]})

    zusammen = (f"Phase-A-Tageslauf: {len(plan)} Plan-Aktion(en)"
                + (f", LLM: {entscheidung['aktionen']}" if entscheidung else
                   ", ohne LLM-Entscheidung"))
    journal.lauf_abschliessen(lauf_id, "ok", zusammen)
    log(f"Dirigent-Lauf {lauf_id} abgeschlossen: {zusammen}")
    return {"status": "ok", "lauf_id": lauf_id, "plan": plan,
            "entscheidung": entscheidung, "lage": lage}
