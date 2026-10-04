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
from datetime import datetime
from pathlib import Path

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

# F-1 (Review 29.09.): tolerant gegen Markdown-Betonung (**), Gross-/Klein-
# Schreibung und Leerzeichen um den Doppelpunkt; Treffer nur am Zeilenanfang.
_EINORDNUNG_RE = re.compile(
    r"(?im)^[^\S\r\n]*\**[^\S\r\n]*EINORDNUNG[^\S\r\n]*\**[^\S\r\n]*:"
    r"[^\S\r\n]*\**[^\S\r\n]*(KONFORM|AUFFAELLIG|STILBRUCH|KEINE_NEUEN_TRADES)")
_EINORDNUNG_ALLE = ("KONFORM", "AUFFAELLIG", "STILBRUCH", "KEINE_NEUEN_TRADES")


def kandidaten(settings: dict | None = None) -> list[dict]:
    """Alle 🟢/🟡-Signale aus der DB (Ampel exakt wie die Ergebnis-Ansicht),
    inkl. Quellen-Feld — der Tageslauf filtert MQL5 heraus (B4)."""
    from ..pipeline import results_from_db  # spät: kein Kreisimport
    ergebnisse = results_from_db(settings)
    return [{"id": r.id, "name": r.name, "platform": getattr(r, "platform", ""),
             "ampel": r.ampel, "quelle": getattr(r, "quelle", "mql5") or "mql5"}
            for r in ergebnisse if r.ampel in ("🟢", "🟡")
            and getattr(r, "forensik_vorhanden", False)]


def mql5_kandidaten(settings: dict | None = None) -> tuple[list[dict], int]:
    """MQL5-🟢/🟡 plus Anzahl übersprungener Quellen-Signale.

    B4 (Intensiv-Review 29./30.09.2026): Der Betreuer prüft über den
    MQL5-Export und destilliert von mql5.com — für Quellen-Signale
    (pelik/robo/vant/zulu) hätte er keinen Export-Weg und würde täglich
    fehlschlagen (16 von 23 Zielen im Ziellauf). Quellen-Signale werden
    SAUBER übersprungen und im Tageslauf protokolliert, bis die Umstellung
    auf den Quellen-Cache (doc/20 Stufe 3) gebaut ist.
    """
    alle = kandidaten(settings)
    nur_mql5 = [k for k in alle if k.get("quelle", "mql5") == "mql5"]
    return nur_mql5, len(alle) - len(nur_mql5)


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


def _snapshot_sha(signal_id: int) -> tuple[str | None, str | None, str | None]:
    """Vergleichs-Stand: der letzte GEPRÜFTE Stand des Signals.

    F-2 (Review 29.09.): trade_files wird nur vom Scan fortgeschrieben —
    verglich der Betreuer dagegen, kumulierte das Delta täglich (Tag n
    enthielt Tage 1..n), das LLM prüfte alte Trades erneut und ein
    STILBRUCH-Alert wiederholte sich. Massgeblich ist der neu_sha des
    letzten Betreuter-Deltas; nur beim ersten Lauf fällt der Vergleich auf
    den Scan-Stand zurück. Rueckgabe (sha, diff_pfad, delta_ts): diff_pfad
    ist die (aeltere) Scan-Datei fuer den Inhaltsgleich, delta_ts begrenzt
    zusaetzlich auf Trades, die NACH der letzten Pruefung geschlossen
    wurden — so kumuliert auch ein zwischenzeitlicher Scan nichts.
    """
    with db._connect() as conn:
        delta = conn.execute(
            "SELECT neu_sha256, ts FROM trade_deltas WHERE signal_id=? "
            "ORDER BY id DESC LIMIT 1", (signal_id,)).fetchone()
        row = conn.execute("SELECT sha256, path FROM trade_files WHERE signal_id=?",
                           (signal_id,)).fetchone()
    alt_pfad = row["path"] if row else None
    if delta and delta["neu_sha256"]:
        return delta["neu_sha256"], alt_pfad, delta["ts"]
    return ((row["sha256"], alt_pfad, None) if row else (None, None, None))


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
            prompt=prompt, modell=modell, tokens=meta.get("total_tokens", client.usage.total_tokens) or 0,
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
    """'EINORDNUNG: X' aus der Antwort schneiden (Rest = Begründungstext).

    F-1 (Review 29.09.): Ein Echo der Optionsliste („EINORDNUNG: KONFORM |
    AUFFAELLIG | …") ist KEINE Bewertung, sondern wiederholte Vorgabe —
    mehr als ein Kandidat in der Trefferzeile gilt als mehrdeutig und wird
    vorsichtig AUFFAELLIG geführt (nie still KONFORM).
    """
    fund = _EINORDNUNG_RE.search(antwort)
    if not fund:
        return "AUFFAELLIG", ("Antwort ohne EINORDNUNG-Zeile — vorsichtig als "
                              "auffällig geführt:\n" + antwort)
    zeilen_ende = antwort.find("\n", fund.start())
    zeile = antwort[fund.start():zeilen_ende if zeilen_ende >= 0 else len(antwort)]
    treffer = [w for w in _EINORDNUNG_ALLE
               if re.search(rf"\b{w}\b", zeile, re.IGNORECASE)]
    if len(treffer) > 1:
        return "AUFFAELLIG", ("Einordnungs-Zeile mehrdeutig (Optionsliste "
                              "wiederholt statt bewertet):\n" + antwort)
    einordnung = fund.group(1)
    text = antwort[fund.end():].strip()
    return einordnung, text or "(keine Begründung geliefert)"


def signal_pruefen(signal: dict, settings: dict, log=print,
                   session: Mql5Session | None = None,
                   quelle: str = "daemon") -> dict:
    """Ein Signal im Tagesdurchlauf prüfen (ein eigener Betreuer-Lauf).

    Ohne übergebene Session wird eine eigene gebaut (Einzelabruf/CLI) —
    der Tageslauf übergibt EINE Session für alle Signale, damit der
    Rate-Limiter über den ganzen Lauf gemeinsam pacingt. quelle reist mit
    (gui/cli/daemon), damit „Letzte Läufe" den echten Auslöser zeigt.
    """
    session = session if session is not None else Mql5Session(settings)
    lauf_id = journal.lauf_starten("betreuer", quelle=quelle,
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
    alt_sha, alt_pfad, delta_ts = _snapshot_sha(signal["id"])
    journal.schritt_protokollieren(
        lauf_id, "betreuer", "export", status="ok",
        detail={"signal": name, "aus_cache": aus_cache,
                "neu_sha256": neu_sha[:16], "alt_sha256": (alt_sha or "")[:16]})
    if alt_sha == neu_sha:
        journal.schritt_protokollieren(
            lauf_id, "betreuer", "sha_vergleich", status="ok",
            detail={"signal": name, "ergebnis": "unveraendert",
                    "hinweis": "kein Modellaufruf"})
        # F-6 (Review 29.09.): Die taegliche KEINE_NEUEN_TRADES-Zeile
        # verdraengte echte Befunde aus letzte_beobachtungen — nur
        # schreiben, wenn die letzte Beobachtung eine ANDERE war.
        letzte = dossier.beobachtungen_lesen(signal["id"], limit=1)
        if not letzte or letzte[0]["einordnung"] != "KEINE_NEUEN_TRADES":
            dossier.beobachtung_speichern(
                signal["id"], "KEINE_NEUEN_TRADES",
                "Export unverändert (SHA identisch) — kein Modellaufruf nötig.")
        return {"signal": name, "einordnung": "KEINE_NEUEN_TRADES",
                "zusammenfassung": f"{name}: keine neuen Trades"}

    # Review 04.10.: Gespeicherte Alt-Snapshots koennen fehlen (Pfad-
    # Migration nach Projektumbenennung, aufgeraeumter Cache) — vorher
    # stuerzte der Betreuer-Lauf mit FileNotFoundError ab und die Karte
    # blieb tagelang auf 'fehler'. Ohne Alt-Stand zaehlt das Delta den
    # kompletten Bestand als neu (dokumentiertes Erst-Delta-Verhalten).
    if alt_pfad and not Path(alt_pfad).exists():
        journal.schritt_protokollieren(
            lauf_id, "betreuer", "alt_snapshot", status="ok",
            detail={"signal": name, "hinweis":
                    "Alt-Snapshot fehlt am gespeicherten Pfad — "
                    "Delta zählt den kompletten Bestand (Erst-Delta)."})
        alt_pfad = None
    neue = delta.neue_trades(alt_pfad, pfad)
    if delta_ts:
        # F-2: Nur Trades nach der letzten Pruefung zaehlen — sonst
        # kumuliert der Datei-Diff gegen den (aelteren) Scan-Stand.
        try:
            stichtag = datetime.fromisoformat(delta_ts)
        except ValueError:
            stichtag = None
        if stichtag:
            neue = [t for t in neue if t.close_time > stichtag]
    kzz = delta.kennzahlen(neue)
    journal.schritt_protokollieren(
        lauf_id, "betreuer", "delta", status="ok",
        detail={"signal": name, "neue_trades": len(neue),
                "kennzahlen": kzz})
    if not neue:
        # Geänderte Datei, aber keine neuen FILLED-Trades (z. B. nur Kontobewegung)
        delta_id = dossier.delta_speichern(signal["id"], alt_sha, neu_sha,
                                           0, kzz)
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
        # F-6 (Review 29.09.): Betriebsstoerung (kein Key, Budget leer,
        # API-Fehler) ist KEINE Handelsauffaelligigkeit — eigener Status,
        # und das Delta gilt als NICHT verbraucht (kein delta_speichern),
        # damit der naechste Lauf dieselben Trades erneut prueft.
        journal.schritt_protokollieren(
            lauf_id, "betreuer", "delta", status="skipped",
            detail={"signal": name, "grund": "LLM nicht verfuegbar — "
                    "Delta nicht als geprueft markiert"})
        dossier.beobachtung_speichern(
            signal["id"], "NICHT_GEPRUEFT",
            "LLM-Prüfung nicht möglich (Key/Budget/API) — Delta-Kennzahlen "
            "im Protokoll (Schritt 'delta'); Prüfung wird im nächsten Lauf "
            "wiederholt.")
        return {"signal": name, "einordnung": "NICHT_GEPRUEFT",
                "zusammenfassung": f"{name}: LLM-Prüfung nicht möglich, "
                                    "wird wiederholt"}
    antwort, schritt_id = llm
    einordnung, text = _einordnung_parsen(antwort)
    delta_id = dossier.delta_speichern(signal["id"], alt_sha, neu_sha,
                                       len(neue), kzz)
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
    signale, uebersprungen = mql5_kandidaten(settings)
    if nur_signal_ids is not None:
        signale = [s for s in signale if s["id"] in nur_signal_ids]
    log(f"Betreuer-Tageslauf: {len(signale)} Kandidat(en).")
    if uebersprungen:
        log(f"Betreuer: {uebersprungen} Quellen-Signal(e) (🟢/🟡, z. B. pelik) "
            "übersprungen — Betreuer prüft bisher nur den MQL5-Weg "
            "(doc/20 Stufe 3: Quellen-Cache offen).")
    session = Mql5Session(settings)
    ergebnisse = [signal_pruefen(s, settings, log, session=session,
                                  quelle=quelle)
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
