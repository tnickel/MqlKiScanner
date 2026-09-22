# -*- coding: utf-8 -*-
"""Chefermittler — Wochen-/Monats-Lagebericht (Phase E, doc/19 §4.4).

Synthese über alle Dossiers, die Marktkontexte der Woche und das
Ampel-Wechsel-Protokoll. Der Lagebericht landet als eigene Meldungsart im
Postfach (doc/19 §8.3). Er EMPFIEHLT — er entscheidet nichts und bewertet
nichts neu (Engine-Bindung); Widersprüche zwischen Bericht und Engine
gelten zugunsten der Engine.

Takt: sonntags abends (nach dem Teilscan des Tages) und am 1. Werktag
des Monats (nach dem Full-Scan). Läuft ein Scan noch, verschiebt sich der
Bericht automatisch zum nächsten Tick — wie der Digest des Melders.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from .. import config, db
from ..llm import client as llm_client
from . import dossier, journal, rollen, rollen_prompts

# Sonntags-Lagebericht ab dieser Stunde (Scan startet 12:00).
ABEND_STUNDE = 18


def _wochenfenster(tage: int = 7) -> str:
    seit = (datetime.now() - timedelta(days=tage)).strftime("%Y-%m-%d")
    return seit


def dossiers_kompakt() -> list[dict]:
    """Je 🟢/🟡-Kandidat die Dossier-Spitze für den Lagebericht (maschinell)."""
    from . import betreuer  # spät: kein Kreisimport
    seit = _wochenfenster()
    kompakt = []
    for kandidat in betreuer.kandidaten():
        signal_id = kandidat["id"]
        profil = dossier.profil_lesen(signal_id)
        beob = dossier.beobachtungen_lesen(signal_id, limit=30)
        von_woche = [b for b in beob if b["ts"] >= seit]
        einordnungen = {e: sum(1 for b in von_woche if b["einordnung"] == e)
                        for e in dossier.EINORDNUNGEN}
        stilbrueche = [b for b in von_woche if b["einordnung"] == "STILBRUCH"]
        kompakt.append({
            "signal": kandidat["name"], "id": signal_id,
            "ampel": kandidat["ampel"],
            "profil_version": (profil or {}).get("version"),
            "beobachtungen_7t": einordnungen,
            "letzte_einordnung": beob[0]["einordnung"] if beob else None,
            "stilbrueche_7t": [{"ts": s["ts"], "text": s["text"][:200]}
                               for s in stilbrueche],
        })
    return kompakt


def _marktkontexte_der_woche() -> list[str]:
    from . import markt  # spät: kein Kreisimport
    markt.init_markt()
    seit = _wochenfenster()
    with db._connect() as conn:
        rows = conn.execute(
            "SELECT ts, lage_text FROM markt_kontext WHERE ts >= ? "
            "ORDER BY id", (seit,)).fetchall()
    return [f"{r['ts']}: {r['lage_text']}" for r in rows]


def _wechsel_der_woche() -> list[dict]:
    seit = _wochenfenster()
    return [{"name": w.get("name"), "signal_id": w.get("signal_id"),
             "wechsel": f"{w.get('ampel_alt') or '—'} → {w.get('ampel_neu')}",
             "richtung": w.get("richtung"), "ts": w.get("ts")}
            for w in db.list_ampel_wechsel(limit=100)
            if str(w.get("ts") or "") >= seit]


def lagebericht(quelle: str = "daemon", log=print,
                settings: dict | None = None) -> dict:
    """Ein Lagebericht in das Postfach; verschiebt sich bei laufendem Scan."""
    settings = settings if settings is not None else config.load_settings()
    aktive_scans = [eintrag for eintrag in journal.aktive_laeufe("dirigent")
                    if eintrag["quelle"] == "daemon"]
    lauf_id = journal.lauf_starten("chef", quelle=quelle)
    if aktive_scans:
        grund = (f"Scan-Lauf {aktive_scans[0]['id']} noch aktiv — "
                 "Lagebericht verschiebt sich zum nächsten Tick.")
        journal.schritt_protokollieren(lauf_id, "chef", "lagebericht",
                                       status="skipped",
                                       detail={"grund": grund})
        aktion = "Wochen-Lagebericht erstellen"
        resultat = f"Verschoben: Scan-Lauf #{aktive_scans[0]['id']} noch aktiv."
        journal.lauf_abschliessen(lauf_id, "skipped", grund,
                                  aktion=aktion, resultat=resultat)
        return {"status": "skipped", "grund": grund, "lauf_id": lauf_id,
                "aktion": aktion, "resultat": resultat}

    grundlage = {
        "dossiers": dossiers_kompakt(),
        "marktkontexte": _marktkontexte_der_woche(),
        "ampel_wechsel": _wechsel_der_woche(),
        "budget": {"tokens_heute": journal.tokens_heute(),
                   "tokens_monat": journal.tokens_monat(),
                   "monatsbudget": int(settings.get(
                       "agenten_monatsbudget_tokens", 5_000_000))},
    }
    journal.schritt_protokollieren(lauf_id, "chef", "grundlage",
                                   detail={"dossiers":
                                           len(grundlage["dossiers"]),
                                           "wechsel":
                                           len(grundlage["ampel_wechsel"])})
    text = _llm_bericht(grundlage, settings, lauf_id, log)
    quelle_text = "LLM-Fassung"
    if text is None:
        text = _code_bericht(grundlage)
        quelle_text = "maschinelle Fassung"
    meldung_id = journal.meldung_speichern(
        "lagebericht", f"Lagebericht ({datetime.now():%d.%m.%Y %H:%M})",
        text, prioritaet=1, quellen=[f"lauf#{lauf_id}"])
    aktion = "Wochen-Lagebericht aus Marktdaten, Dossiers & Ampelwechseln aggregiert"
    resultat = f"Lagebericht #{meldung_id} erstellt und im Postfach abgelegt ({quelle_text})."
    journal.lauf_abschliessen(lauf_id, "ok",
                              f"{aktion}: {resultat}",
                              aktion=aktion, resultat=resultat)
    log(f"Chefermittler: Lagebericht #{meldung_id} ({quelle_text}).")
    return {"status": "ok", "lauf_id": lauf_id, "meldung_id": meldung_id,
            "text": text, "aktion": aktion, "resultat": resultat}


def _llm_bericht(grundlage: dict, settings: dict, lauf_id: int,
                 log) -> str | None:
    modell = settings.get("agenten_chef_modell", rollen.STANDARD_MODELL)
    max_tokens = int(settings.get("agenten_chef_max_tokens", 16384))
    budget_rest = max(0, int(settings.get("agenten_tagesbudget_tokens",
                                          500_000)) - journal.tokens_heute())
    client = llm_client.GlmClient(
        model_stufe1=settings.get("model_stufe1", config.MODEL_STUFE1),
        model_stufe2=settings.get("model_stufe2", config.MODEL_STUFE2),
        max_total_tokens=budget_rest or 1,
        base_url=settings.get("glm_base_url") or None,
        timeout=2400,
    )
    if not client.has_key or budget_rest <= 0:
        journal.schritt_protokollieren(
            lauf_id, "chef", "llm_lagebericht", status="skipped",
            detail={"grund": "Kein Key oder Tagesbudget erschöpft — "
                             "maschinelle Fassung."})
        return None
    prompt = rollen_prompts.fuellung(
        rollen_prompts.lade_vorlage("lagebericht"),
        {"dossiers_json": json.dumps(grundlage["dossiers"],
                                     ensure_ascii=False, indent=2),
         "marktkontext_woche": "\n\n".join(grundlage["marktkontexte"])
         or "(keine Marktkontexte in der Woche)",
         "ampel_wechsel_json": json.dumps(grundlage["ampel_wechsel"],
                                          ensure_ascii=False, indent=2),
         "budget_status": json.dumps(grundlage["budget"],
                                     ensure_ascii=False)})
    meta: dict = {}
    import time as _time
    beginn = _time.monotonic()
    try:
        antwort = client.chat(prompt, model=modell, stufe=2,
                              max_tokens=max_tokens, meta_out=meta)
    except llm_client.LlmError as exc:
        journal.schritt_protokollieren(
            lauf_id, "chef", "llm_lagebericht", status="fehler",
            prompt=prompt, modell=modell, tokens=client.usage.total_tokens,
            dauer_s=round(_time.monotonic() - beginn, 1),
            detail={"fehler": str(exc)})
        log(f"  Chef-LLM fehlgeschlagen: {exc}")
        return None
    journal.schritt_protokollieren(
        lauf_id, "chef", "llm_lagebericht", prompt=prompt, antwort=antwort,
        modell=modell, tokens=meta.get("total_tokens",
                                       client.usage.total_tokens) or 0,
        dauer_s=meta.get("dauer_s"))
    return antwort


def _code_bericht(grundlage: dict) -> str:
    """Maschinelle Fassung — Zahlen aus der Grundlage zitiert."""
    zeilen = [f"Kandidaten im Blick: {len(grundlage['dossiers'])}."]
    for d in grundlage["dossiers"]:
        zeilen.append(f"- {d['signal']} ({d['ampel']}): letzte Einordnung "
                      f"{d['letzte_einordnung']}, Beobachtungen 7 T "
                      f"{d['beobachtungen_7t']}"
                      + (f", {len(d['stilbrueche_7t'])} STILBRUCH/STILBRÜCHE"
                         if d["stilbrueche_7t"] else ""))
    zeilen.append(f"Ampel-Wechsel der Woche: {len(grundlage['ampel_wechsel'])}.")
    zeilen.append(f"Marktkontexte der Woche: {len(grundlage['marktkontexte'])}.")
    zeilen.append(f"Token-Monatsbudget: {grundlage['budget']['tokens_monat']} "
                  f"von {grundlage['budget']['monatsbudget']}.")
    return "Lagebericht (maschinelle Fassung):\n" + "\n".join(zeilen)
