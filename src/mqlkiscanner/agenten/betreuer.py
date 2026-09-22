# -*- coding: utf-8 -*-
"""Signal-Betreuer — tägliche Trade-Delta-Prüfung (Phase B, doc/19 §4.3).

Ablauf je 🟢/🟡-Signal:
1. Export holen (MQL5-Session mit Rate-Limiter und 20-h-Cache — ToS schonen;
   der Cache der GUI-Scans wird mitbenutzt, ein heutiger GUI-Scan macht den
   Abruf zum No-Op, weil der Hash dann schon stimmt).
2. SHA-256 gegen den letzten Snapshot (db.trade_files): unverändert →
   Journal-Eintrag, KEIN Modellaufruf.
3. Neue Trades → Delta-Kennzahlen (delta.py, reiner Code) → LLM-Prüfung
   gegen das Algo-Profil (betreuer_delta) → Einordnung
   KONFORM/AUFFAELLIG/STILBRUCH → Dossier-Beobachtung mit LLM-Nachweis.
4. Fehlt das Profil: einmalig destillieren (destillation.py) — ohne
   Belegbasis oder Key wird das protokolliert, nicht erfunden.

Die Einordnung ist Beobachtung, niemals Neubewertung: Ampel, Urteil und
Score ändert nur die Engine in regulären Scan-Läufen.
"""
from __future__ import annotations

import json
import re

from .. import config, db
from ..llm import client as llm_client
from ..mql5.session import Mql5Session
from . import delta, dossier, journal, markt, rollen, rollen_prompts
from . import destillation, melder

# Export-Cache: 20 h — der tägliche 06:45-Abruf holt frisch, ein GUI-Scan
# am Vorabend macht daraus einen No-Op (Hash identisch).
CACHE_STUNDEN = 20.0


def _marktkontext_text() -> str:
    """Heutige Marktlage für den Betreuer-Prompt; klarer Platzhalter, wenn
    der Marktbeobachter (noch) keinen Kontext geliefert hat."""
    kontext = markt.kontext_heute()
    if not kontext:
        return ("Kein Marktkontext verfügbar (Marktbeobachter lief heute nicht "
                "— z. B. Terminal aus oder Wochenende).")
    return f"Marktlage ({kontext['ts']}, Quelle: Marktbeobachter):\n{kontext['lage']}"

_EINORDNUNG_RE = re.compile(
    r"EINORDNUNG:\s*(KONFORM|AUFFAELLIG|STILBRUCH|KEINE_NEUEN_TRADES)")


def kandidaten(settings: dict | None = None) -> list[dict]:
    """Alle 🟢/🟡-Signale aus der DB (Ampel exakt wie die Ergebnis-Ansicht)."""
    from ..pipeline import results_from_db  # spät: kein Kreisimport
    ergebnisse = results_from_db(settings)
    return [{"id": r.id, "name": r.name, "platform": getattr(r, "platform", ""),
             "ampel": r.ampel}
            for r in ergebnisse if r.ampel in ("🟢", "🟡")
            and getattr(r, "forensik_vorhanden", False)]


def export_holen(session: Mql5Session, signal: dict, settings: dict) -> tuple[str, bool]:
    """Trade-Export laden (Pfad, aus_cache). Tests stubben diese Funktion.

    Eine Session für den GESAMTEN Tageslauf (gemeinsamer Rate-Limiter);
    die Zwischen-Signal-Pause entspricht der Pipeline (GUI-Parität).
    """
    from ..mql5.exporter import export_positions  # spät, mock-freundlich
    return export_positions(
        session, signal["id"], cache_stunden=CACHE_STUNDEN,
        extra_pause_s=float(settings.get("rate_pause_zwischen_signalen_s", 5.0)),
        platform=signal.get("platform") or None)


def _snapshot_sha(signal_id: int) -> tuple[str | None, str | None]:
    with db._connect() as conn:
        row = conn.execute("SELECT sha256, path FROM trade_files WHERE signal_id=?",
                           (signal_id,)).fetchone()
    return (row["sha256"], row["path"]) if row else (None, None)


def _llm_einordnung(signal_id: int, signal_name: str, profil_text: str,
                    delta_json: str, settings: dict,
                    lauf_id: int) -> tuple[str, str] | None:
    """LLM-Prüfung gegen das Profil; None = übersprungen/fehlgeschlagen."""
    modell = settings.get("agenten_betreuer_modell", rollen.STANDARD_MODELL)
    max_tokens = int(settings.get("agenten_betreuer_max_tokens", 8192))
    budget_rest = max(0, int(settings.get("agenten_tagesbudget_tokens",
                                          500_000)) - journal.tokens_heute())
    client = llm_client.GlmClient(
        model_stufe1=settings.get("model_stufe1", config.MODEL_STUFE1),
        model_stufe2=settings.get("model_stufe2", config.MODEL_STUFE2),
        max_total_tokens=budget_rest or 1,
        base_url=settings.get("glm_base_url") or None,
        timeout=2400,
    )
    if not client.has_key:
        journal.schritt_protokollieren(
            lauf_id, "betreuer", "llm_pruefung", status="skipped",
            detail={"grund": "Kein GLM-Key gesetzt.", "signal": signal_name})
        return None
    if budget_rest <= 0:
        journal.schritt_protokollieren(
            lauf_id, "betreuer", "llm_pruefung", status="skipped",
            detail={"grund": "Tagesbudget erschöpft.", "signal": signal_name})
        return None
    prompt = rollen_prompts.fuellung(
        rollen_prompts.lade_vorlage("betreuer_delta"),
        {"signal_name": signal_name, "profil_text": profil_text,
         "delta_json": delta_json, "marktkontext": _marktkontext_text(),
         "letzte_beobachtungen": dossier.letzte_beobachtungen(signal_id)})
    meta: dict = {}
    import time as _time
    beginn = _time.monotonic()
    try:
        antwort = client.chat(prompt, model=modell, stufe=2,
                              max_tokens=max_tokens, meta_out=meta)
    except llm_client.LlmError as exc:
        journal.schritt_protokollieren(
            lauf_id, "betreuer", "llm_pruefung", status="fehler",
            prompt=prompt, modell=modell, tokens=client.usage.total_tokens,
            dauer_s=round(_time.monotonic() - beginn, 1),
            detail={"fehler": str(exc), "signal": signal_name})
        return None
    schritt = journal.schritt_protokollieren(
        lauf_id, "betreuer", "llm_pruefung", prompt=prompt, antwort=antwort,
        modell=modell, tokens=meta.get("total_tokens",
                                       client.usage.total_tokens) or 0,
        dauer_s=meta.get("dauer_s"), detail={"signal": signal_name})
    return antwort, schritt


def _einordnung_parsen(antwort: str) -> tuple[str, str]:
    """'EINORDNUNG: X' aus der Antwort schneiden (Rest = Begründungstext)."""
    fund = _EINORDNUNG_RE.search(antwort)
    if not fund:
        return "AUFFAELLIG", ("Antwort ohne EINORDNUNG-Zeile — vorsichtig als "
                              "auffällig geführt:\n" + antwort)
    einordnung = fund.group(1)
    text = antwort[fund.end():].strip()
    return einordnung, text or "(keine Begründung geliefert)"


def signal_pruefen(signal: dict, settings: dict, log=print,
                   session: Mql5Session | None = None) -> dict:
    """Ein Signal im Tagesdurchlauf prüfen (ein eigener Betreuer-Lauf).

    Ohne übergebene Session wird eine eigene gebaut (Einzelabruf/CLI) —
    der Tageslauf übergibt EINE Session für alle Signale, damit der
    Rate-Limiter über den ganzen Lauf gemeinsam pacingt.
    """
    session = session if session is not None else Mql5Session(settings)
    lauf_id = journal.lauf_starten("betreuer", quelle="daemon",
                                   signal_id=signal["id"])
    try:
        ergebnis = _signal_pruefen_inner(signal, settings, session,
                                         lauf_id, log)
        aktion = f"Handelsmuster von »{signal['name']}« geprüft"
        resultat = ergebnis.get("resultat") or ergebnis.get("zusammenfassung") or "Konform"
        journal.lauf_abschliessen(lauf_id, "ok",
                                  zusammenfassung=ergebnis["zusammenfassung"],
                                  aktion=aktion, resultat=resultat)
        return ergebnis | {"lauf_id": lauf_id, "status": "ok",
                           "aktion": aktion, "resultat": resultat}
    except Exception as exc:  # Ein Signal darf den Gesamtlauf nicht abreißen
        journal.schritt_protokollieren(lauf_id, "betreuer", "fehler",
                                       status="fehler",
                                       detail={"fehler": str(exc),
                                               "signal": signal["name"]})
        aktion = f"Signalprüfung »{signal['name']}«"
        resultat = f"Fehler: {exc}"
        journal.lauf_abschliessen(lauf_id, "fehler", str(exc),
                                  aktion=aktion, resultat=resultat)
        log(f"  Betreuer {signal['name']} fehlgeschlagen: {exc}")
        return {"status": "fehler", "grund": str(exc), "lauf_id": lauf_id,
                "signal": signal["name"], "aktion": aktion, "resultat": resultat}


def _signal_pruefen_inner(signal: dict, settings: dict, session: Mql5Session,
                           lauf_id: int, log) -> dict:
    name = signal["name"]
    # Profil fehlt? Erst destillieren (einmalig, protokolliert).
    profil = dossier.profil_lesen(signal["id"])
    if profil is None:
        url = f"https://www.mql5.com/en/signals/{signal['id']}"
        destillation.profil_erstellen(signal["id"], name, url, settings,
                                      lauf_id=lauf_id, log=log)
        profil = dossier.profil_lesen(signal["id"])
    if profil is None:
        grund = "Kein Profil verfügbar (Belegbasis/Key fehlt) — Prüfung entfällt."
        journal.schritt_protokollieren(lauf_id, "betreuer", "pruefung",
                                       status="skipped",
                                       detail={"grund": grund, "signal": name})
        return {"signal": name, "zusammenfassung": grund,
                "einordnung": None}

    pfad, aus_cache = export_holen(session, signal, settings)
    neu_sha = delta.datei_sha256(pfad)
    alt_sha, alt_pfad = _snapshot_sha(signal["id"])
    journal.schritt_protokollieren(
        lauf_id, "betreuer", "export", status="ok",
        detail={"signal": name, "aus_cache": aus_cache,
                "neu_sha256": neu_sha[:16], "alt_sha256": (alt_sha or "")[:16]})
    if alt_sha == neu_sha:
        journal.schritt_protokollieren(
            lauf_id, "betreuer", "sha_vergleich", status="ok",
            detail={"signal": name, "ergebnis": "unveraendert",
                    "hinweis": "kein Modellaufruf"})
        dossier.beobachtung_speichern(
            signal["id"], "KEINE_NEUEN_TRADES",
            "Export unverändert (SHA identisch) — kein Modellaufruf nötig.")
        return {"signal": name, "einordnung": "KEINE_NEUEN_TRADES",
                "zusammenfassung": f"{name}: keine neuen Trades"}

    neue = delta.neue_trades(alt_pfad, pfad)
    kzz = delta.kennzahlen(neue)
    delta_id = dossier.delta_speichern(signal["id"], alt_sha, neu_sha,
                                       len(neue), kzz)
    journal.schritt_protokollieren(
        lauf_id, "betreuer", "delta", status="ok",
        detail={"signal": name, "neue_trades": len(neue),
                "delta_id": delta_id, "kennzahlen": kzz})
    if not neue:
        # Geänderte Datei, aber keine neuen FILLED-Trades (z. B. nur Kontobewegung)
        dossier.beobachtung_speichern(
            signal["id"], "KEINE_NEUEN_TRADES",
            "Exportdatei geändert, aber keine neuen gefüllten Trades "
            "(Kennzahlen leer).", delta_ref=delta_id)
        return {"signal": name, "einordnung": "KEINE_NEUEN_TRADES",
                "zusammenfassung": f"{name}: Datei geändert, keine neuen Trades"}

    llm = _llm_einordnung(signal["id"], name, profil["profil_text"],
                          json.dumps(kzz, ensure_ascii=False, indent=2),
                          settings, lauf_id)
    if llm is None:
        grund = "LLM-Prüfung übersprungen — Delta gespeichert, Prüfung wiederholt sich nicht automatisch."
        dossier.beobachtung_speichern(
            signal["id"], "AUFFAELLIG",
            grund + " Delta-Kennzahlen im Protokoll (Schritt 'delta').",
            delta_ref=delta_id)
        return {"signal": name, "einordnung": "AUFFAELLIG",
                "zusammenfassung": f"{name}: {grund}"}
    antwort, schritt_id = llm
    einordnung, text = _einordnung_parsen(antwort)
    beobachtung_id = dossier.beobachtung_speichern(
        signal["id"], einordnung, text, delta_ref=delta_id,
        schritt_ref=schritt_id)
    if einordnung == "STILBRUCH":
        melder.stilbruch_alert(name, text, schritt_id, lauf_id, signal["id"],
                               beobachtung_id=beobachtung_id)
    return {"signal": name, "einordnung": einordnung,
            "zusammenfassung": f"{name}: {einordnung}"}


def tageslauf(quelle: str = "daemon", log=print, settings: dict | None = None,
              nur_signal_ids: list[int] | None = None) -> dict:
    """Alle 🟢/🟡-Signale prüfen; Rückgabe zusammengefasst.

    Eine gemeinsame Mql5Session für alle Signale: ein Login-Check und ein
    gemeinsam pacingender Rate-Limiter statt je Signal neuer Bursts.
    """
    settings = settings if settings is not None else config.load_settings()
    signale = kandidaten(settings)
    if nur_signal_ids is not None:
        signale = [s for s in signale if s["id"] in nur_signal_ids]
    log(f"Betreuer-Tageslauf: {len(signale)} Kandidat(en).")
    session = Mql5Session(settings)
    ergebnisse = [signal_pruefen(s, settings, log, session=session)
                  for s in signale]
    je = {}
    for e in ergebnisse:
        je[e.get("einordnung") or "OHNE"] = je.get(e.get("einordnung") or "OHNE",
                                                    0) + 1
    
    aktion = f"Handelsmuster von {len(signale)} aktiven Signal(en) geprüft"
    if je.get("STILBRUCH", 0) > 0:
        resultat = f"⚠️ STILBRUCH bei {je['STILBRUCH']} Signal(en) erkannt! Sofort-Alert ausgelöst."
    elif je.get("AUFFAELLIG", 0) > 0:
        resultat = f"Auffälligkeiten bei {je['AUFFAELLIG']} Signal(en) im Dossier vermerkt."
    elif je.get("KONFORM", 0) > 0:
        resultat = f"{je['KONFORM']} Signale geprüft: Alle Trade-Muster regelkonform."
    elif je.get("KEINE_NEUEN_TRADES", 0) > 0:
        resultat = f"{len(signale)} Signale unverändert: Keine neuen Trades seit letztem Check."
    else:
        zusammen_roh = ", ".join(f"{k}: {v}" for k, v in sorted(je.items())) or "keine Signale"
        resultat = f"{len(signale)} Signale geprüft: {zusammen_roh}."

    zusammen = f"{aktion}: {resultat}"
    return {"signale": len(signale), "einordnungen": je,
            "zusammenfassung": zusammen, "aktion": aktion, "resultat": resultat,
            "ergebnisse": ergebnisse}
