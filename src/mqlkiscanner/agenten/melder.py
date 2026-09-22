# -*- coding: utf-8 -*-
"""Melder — Alerts und Tagesdigest ins Postfach (Phase D, doc/19 §4.5).

Drei Wege ins Postfach:
1. SOFORT-Alerts: Der Betreuer ruft alert() direkt bei STILBRUCH — keine
   Wartezeit bis zum nächsten Tick.
2. Ampelwechsel-Watcher: pruefe_neue_wechsel() läuft in JEDEM Scheduler-
   Tick und meldet neue Zeilen der Engine-Wechsel-Chronik (aus GUI-Scans
   wie Daemon-Scans — gesehen wird alles, was in die DB geschrieben wurde).
3. Tagesdigest nach dem Betreuer (Takt: Startzeit + 40 min; läuft der
   Betreuer noch, verschiebt sich der Digest automatisch zum nächsten Tick).

Der Melder verdichtet mit dem LLM (Vorlage `meldung`), fällt aber ohne
Key/Budget auf eine maschinelle Fassung zurück — die Meldung kommt immer
an, nur weniger formuliert.
"""
from __future__ import annotations

import json
from datetime import datetime

from .. import config, db
from ..llm import client as llm_client
from . import dossier, journal, rollen, rollen_prompts

STEUERUNG_WECHSEL_KEY = "melder_ampel_wechsel_id"


def alert(typ: str, titel: str, text: str, *, prioritaet: int = 2,
          quellen: list | None = None, quelle: str = "ereignis") -> int:
    """Sofort-Meldung ins Postfach (mit Journaleintrag als Nachweis)."""
    lauf_id = journal.lauf_starten("melder", quelle=quelle)
    journal.schritt_protokollieren(
        lauf_id, "melder", "alert", detail={"typ": typ, "titel": titel,
                                            "prioritaet": prioritaet})
    meldung_id = journal.meldung_speichern(typ, titel, text,
                                           prioritaet=prioritaet,
                                           quellen=quellen or [])
    journal.lauf_abschliessen(lauf_id, "ok", f"Alert: {titel}")
    return meldung_id


def stilbruch_alert(signal_name: str, text: str, schritt_ref: int,
                    lauf_id: int, signal_id: int) -> int:
    """Der Betreuer meldt einen Stilbruch — sofort, prioritaet 3."""
    return alert(
        "alert", f"STILBRUCH: {signal_name}", text,
        prioritaet=3,
        quellen=[f"schritt#{schritt_ref}", f"lauf#{lauf_id}",
                 f"signal#{signal_id}"],
        quelle="betreuer")


def pruefe_neue_wechsel(log=print) -> list[dict]:
    """Neue Ampel-Wechsel melden (Watcher, jeder Tick; idempotent).

    Der letzte bearbeitete Wechsel steht in der Steuerungstabelle — der
    Daemon bemerkt damit auch Wechsel aus GUI-Scans, die er selbst nicht
    angestoßen hat.
    """
    steuer = journal.steuerung_lesen()
    letzte_id = int(steuer.get(STEUERUNG_WECHSEL_KEY) or 0)
    wechsel = [w for w in db.list_ampel_wechsel(limit=100)
               if int(w["id"]) > letzte_id]
    if not wechsel:
        return []
    for w in wechsel:
        richtung = w.get("richtung") or ""
        prioritaet = 3 if richtung == "verschlechterung" else 2
        gruende = w.get("gruende") or []
        grund_text = "; ".join(
            f"{g.get('kriterium', '?')}: {g.get('alt', '?')} → "
            f"{g.get('neu', '?')}" for g in gruende[:3])
        alert("alert",
              f"Ampelwechsel: {w.get('name') or w.get('signal_id')} "
              f"{w.get('ampel_alt') or '—'} → {w.get('ampel_neu')}",
              f"Richtung: {richtung}. {grund_text}",
              prioritaet=prioritaet,
              quellen=[f"ampel_wechsel#{w['id']}",
                       f"signal#{w.get('signal_id')}"],
              quelle="watcher")
    journal.steuerung_setzen(STEUERUNG_WECHSEL_KEY,
                             str(max(int(w["id"]) for w in wechsel)))
    log(f"Melder: {len(wechsel)} neue Ampel-Wechsel gemeldet.")
    return wechsel


def _ereignisse_heute(settings: dict) -> dict:
    """DeterministischeDigest-Grundlage — alles maschinell gezählt."""
    heute = datetime.now().strftime("%Y-%m-%d")
    laeufe = journal.list_laeufe(limit=200)
    von_heute = [l for l in laeufe if l["start"].startswith(heute)]
    je_status: dict[str, int] = {}
    fehler: list[str] = []
    for l in von_heute:
        je_status[l["status"]] = je_status.get(l["status"], 0) + 1
        if l["status"] == "fehler":
            fehler.append(f"{l['rolle']}/{l['signal_id'] or '-'}: "
                          f"{(l['zusammenfassung'] or '')[:120]}")
    # Beobachtungen heute direkt aus dem Dossier (je Einordnung).
    dossier.init_dossier()
    with db._connect() as conn:
        rows = conn.execute(
            "SELECT einordnung, COUNT(*) AS n FROM dossier_beobachtungen "
            "WHERE ts LIKE ? GROUP BY einordnung", (heute + "%",)).fetchall()
    beobachtungen = {r["einordnung"]: int(r["n"]) for r in rows}
    wechsel_heute = [w for w in db.list_ampel_wechsel(limit=100)
                     if str(w.get("ts") or "").startswith(heute)]
    steuer = journal.steuerung_lesen()
    return {
        "datum": heute,
        "laeufe_heute": {"anzahl": len(von_heute), "je_status": je_status,
                         "fehler": fehler[:5]},
        "beobachtungen": beobachtungen,
        "ampel_wechsel_heute": [{"name": w.get("name"),
                                 "wechsel": f"{w.get('ampel_alt') or '—'} → "
                                            f"{w.get('ampel_neu')}",
                                 "richtung": w.get("richtung")}
                                for w in wechsel_heute],
        "markt_tick": steuer.get("letzter_tick") or "",
        "tokens_heute": journal.tokens_heute(),
        "tagesbudget": int(settings.get("agenten_tagesbudget_tokens", 500_000)),
        "postfach_gesamt": journal.meldungen_zaehlen(),
    }


def tagesdigest(quelle: str = "daemon", log=print,
                settings: dict | None = None) -> dict:
    """Tagesdigest nach dem Betreuer; verschiebt sich, solange dieser läuft."""
    settings = settings if settings is not None else config.load_settings()
    aktive_betreuer = journal.aktive_laeufe("betreuer")
    lauf_id = journal.lauf_starten("melder", quelle=quelle)
    if aktive_betreuer:
        grund = (f"Betreuer noch aktiv (Lauf {aktive_betreuer[0]['id']}) — "
                 "Digest verschiebt sich zum nächsten Tick.")
        journal.schritt_protokollieren(lauf_id, "melder", "digest",
                                       status="skipped", detail={"grund": grund})
        journal.lauf_abschliessen(lauf_id, "skipped", grund)
        return {"status": "skipped", "grund": grund, "lauf_id": lauf_id}

    ereignisse = _ereignisse_heute(settings)
    journal.schritt_protokollieren(lauf_id, "melder", "grundlage",
                                   detail=ereignisse)
    text = _llm_digest(ereignisse, settings, lauf_id, log)
    quelle_text = "LLM-Fassung"
    if text is None:
        text = _code_digest(ereignisse)
        quelle_text = "maschinelle Fassung"
    meldung_id = journal.meldung_speichern(
        "digest", f"Tagesdigest {ereignisse['datum']}", text, prioritaet=1,
        quellen=[f"lauf#{lauf_id}"])
    journal.lauf_abschliessen(lauf_id, "ok",
                              f"Tagesdigest ({quelle_text}) ins Postfach.")
    log(f"Melder: Tagesdigest #{meldung_id} ({quelle_text}).")
    return {"status": "ok", "lauf_id": lauf_id, "meldung_id": meldung_id,
            "text": text}


def _llm_digest(ereignisse: dict, settings: dict, lauf_id: int,
                log) -> str | None:
    modell = settings.get("agenten_melder_modell", rollen.STANDARD_MODELL)
    max_tokens = int(settings.get("agenten_melder_max_tokens", 4096))
    budget_rest = max(0, int(settings.get("agenten_tagesbudget_tokens",
                                          500_000)) - journal.tokens_heute())
    client = llm_client.GlmClient(
        model_stufe1=settings.get("model_stufe1", config.MODEL_STUFE1),
        model_stufe2=settings.get("model_stufe2", config.MODEL_STUFE2),
        max_total_tokens=budget_rest or 1,
        base_url=settings.get("glm_base_url") or None,
    )
    if not client.has_key or budget_rest <= 0:
        journal.schritt_protokollieren(
            lauf_id, "melder", "llm_digest", status="skipped",
            detail={"grund": "Kein Key oder Tagesbudget erschöpft — "
                             "maschinelle Fassung."})
        return None
    prompt = rollen_prompts.fuellung(
        rollen_prompts.lade_vorlage("meldung"),
        {"typ": "tagesdigest",
         "ereignisse_json": json.dumps(ereignisse, ensure_ascii=False,
                                       indent=2)})
    meta: dict = {}
    import time as _time
    beginn = _time.monotonic()
    try:
        antwort = client.chat(prompt, model=modell, stufe=2,
                              max_tokens=max_tokens, meta_out=meta)
    except llm_client.LlmError as exc:
        journal.schritt_protokollieren(
            lauf_id, "melder", "llm_digest", status="fehler", prompt=prompt,
            modell=modell, tokens=client.usage.total_tokens,
            dauer_s=round(_time.monotonic() - beginn, 1),
            detail={"fehler": str(exc)})
        log(f"  Melder-LLM fehlgeschlagen: {exc}")
        return None
    journal.schritt_protokollieren(
        lauf_id, "melder", "llm_digest", prompt=prompt, antwort=antwort,
        modell=modell, tokens=meta.get("total_tokens",
                                       client.usage.total_tokens) or 0,
        dauer_s=meta.get("dauer_s"))
    return antwort


def _code_digest(ereignisse: dict) -> str:
    """Maschinelle Fassung ohne LLM — Zahlen aus der Grundlage zitiert."""
    beob = ereignisse.get("beobachtungen") or {}
    wechsel = ereignisse.get("ampel_wechsel_heute") or []
    zeilen = [
        f"Läufe heute: {ereignisse['laeufe_heute']['anzahl']} "
        f"({ereignisse['laeufe_heute']['je_status']}).",
        "Beobachtungen heute: " + (
            ", ".join(f"{k}: {v}" for k, v in sorted(beob.items()))
            or "keine"),
        f"Ampel-Wechsel heute: {len(wechsel)}.",
        f"Token-Verbrauch heute: {ereignisse['tokens_heute']} von "
        f"{ereignisse['tagesbudget']}.",
    ]
    for fehler in ereignisse["laeufe_heute"]["fehler"]:
        zeilen.append(f"Fehler: {fehler}")
    return "Tagesdigest (maschinelle Fassung):\n" + "\n".join(zeilen)
