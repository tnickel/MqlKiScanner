# -*- coding: utf-8 -*-
"""Marktbeobachter — täglicher Marktkontext (Phase C, doc/19 §4.2).

Ablauf: Symbole der Beobachtungsliste bestimmen (automatisch aus den
🟢/🟡-Kandidaten plus manuelle Einträge) → Kurs-Kennzahlen holen
(marktdata, reiner Code, nur lesend) → LLM fasst die Lage in wenige Sätze
→ kontext des Tages speichern. Der Betreuer liest diesen Kontext in
jede Delta-Prüfung; fehlt er (Terminal aus, Wochenende), läuft die Prüfung
mit einem klaren Platzhalter weiter.

Tabelle markt_kontext (append-only): ein Eintrag je erfolgreichem Lauf
mit sämtlichen Kennzahlen und dem Lagentext.
"""
from __future__ import annotations

import json

from .. import config, db
from ..llm import client as llm_client
from . import journal, marktdata, rollen, rollen_prompts


def init_markt() -> None:
    with db._connect() as conn:
        conn.executescript("""
CREATE TABLE IF NOT EXISTS markt_kontext (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ts             TEXT NOT NULL,
    symbole_json   TEXT NOT NULL,
    kennzahlen_json TEXT NOT NULL,
    lage_text      TEXT NOT NULL
);
""")


def beobachtungsliste(settings: dict | None = None) -> list[str]:
    """Manuelle Symbole + Symbole der 🟢/🟡-Kandidaten (aus der Forensik)."""
    settings = settings if settings is not None else config.load_settings()
    symbole: list[str] = []
    for roh in str(settings.get("markt_symbole_manuell") or "").replace(",", " ").split():
        if roh.upper() not in symbole:
            symbole.append(roh.upper())
    from . import betreuer  # spät: kein Kreisimport
    with db._connect() as conn:
        for kandidat in betreuer.kandidaten(settings):
            row = conn.execute("SELECT json FROM forensik WHERE signal_id=?",
                               (kandidat["id"],)).fetchone()
            if not row:
                continue
            try:
                roh_symbole = json.loads(row["json"] or "{}").get("symbole") or ""
            except json.JSONDecodeError:
                roh_symbole = ""
            for einzeln in str(roh_symbole).replace(",", " ").split():
                if einzeln.upper() not in symbole:
                    symbole.append(einzeln.upper())
    return symbole


def tageslauf(quelle: str = "daemon", log=print, settings: dict | None = None,
              kurse_override: dict | None = None) -> dict:
    """Ein Marktbeobachter-Lauf; kurse_override erlaubt Tests/E2E ohne Terminal."""
    settings = settings if settings is not None else config.load_settings()
    init_markt()
    lauf_id = journal.lauf_starten("markt", quelle=quelle)
    symbole = beobachtungsliste(settings)
    journal.schritt_protokollieren(
        lauf_id, "markt", "beobachtungsliste", detail={"symbole": symbole})

    kurse = kurse_override if kurse_override is not None else \
        marktdata.kurse_holen(symbole, settings)
    if not kurse.get("ok"):
        grund = kurse.get("grund", "unbekannter Grund")
        journal.schritt_protokollieren(
            lauf_id, "markt", "kursholen", status="skipped",
            detail={"grund": grund})
        journal.lauf_abschliessen(lauf_id, "skipped", grund)
        log(f"Marktbeobachter übersprungen: {grund}")
        return {"status": "skipped", "grund": grund, "lauf_id": lauf_id}

    kennzahlen = kurse.get("kurse", {})
    journal.schritt_protokollieren(
        lauf_id, "markt", "kursholen", status="ok",
        detail={"terminal": kurse.get("terminal", ""),
                "kennzahlen": kennzahlen,
                "symbole_ohne_daten": kurse.get("symbole_ohne_daten", [])})

    lage = _llm_lage(kennzahlen, symbole, settings, lauf_id, log)
    quelle_lage = "LLM-Lage"
    if lage is None:
        lage = _code_lage(kennzahlen)  # Fallback: knappe maschinelle Fassung
        quelle_lage = "maschinelle Kurzfassung"
    from datetime import datetime
    ts = datetime.now().isoformat(sep=" ", timespec="seconds")
    with db._connect() as conn:
        conn.execute(
            "INSERT INTO markt_kontext (ts, symbole_json, kennzahlen_json, "
            "lage_text) VALUES (?,?,?,?)",
            (ts, json.dumps(symbole, ensure_ascii=False),
             json.dumps(kennzahlen, ensure_ascii=False), lage))
    journal.lauf_abschliessen(
        lauf_id, "ok",
        f"Marktkontext: {len(kennzahlen)} Symbol(e), {quelle_lage}")
    log(f"Marktbeobachter fertig: {len(kennzahlen)} Symbol(e) ({quelle_lage}).")
    return {"status": "ok", "lauf_id": lauf_id, "symbole": list(kennzahlen),
            "kennzahlen": kennzahlen, "lage": lage, "ts": ts}


def _llm_lage(kennzahlen: dict, symbole: list[str], settings: dict,
              lauf_id: int, log) -> str | None:
    """LLM-Kurzfassung der Marktlage; None = übersprungen/fehlgeschlagen."""
    modell = settings.get("agenten_markt_modell", rollen.STANDARD_MODELL)
    max_tokens = int(settings.get("agenten_markt_max_tokens", 4096))
    budget_rest = max(0, int(settings.get("agenten_tagesbudget_tokens",
                                          500_000)) - journal.tokens_heute())
    client = llm_client.GlmClient(
        model_stufe1=settings.get("model_stufe1", config.MODEL_STUFE1),
        model_stufe2=settings.get("model_stufe2", config.MODEL_STUFE2),
        max_total_tokens=budget_rest or 1,
        base_url=settings.get("glm_base_url") or None,
    )
    if not client.has_key:
        journal.schritt_protokollieren(
            lauf_id, "markt", "llm_lage", status="skipped",
            detail={"grund": "Kein GLM-Key gesetzt — maschinelle Kurzfassung."})
        return None
    if budget_rest <= 0:
        journal.schritt_protokollieren(
            lauf_id, "markt", "llm_lage", status="skipped",
            detail={"grund": "Tagesbudget erschöpft — maschinelle Kurzfassung."})
        return None
    prompt = rollen_prompts.fuellung(
        rollen_prompts.lade_vorlage("markt_kontext"),
        {"kurse_json": json.dumps(kennzahlen, ensure_ascii=False, indent=2),
         "symbole_json": json.dumps(symbole, ensure_ascii=False)})
    meta: dict = {}
    import time as _time
    beginn = _time.monotonic()
    try:
        antwort = client.chat(prompt, model=modell, stufe=2,
                              max_tokens=max_tokens, meta_out=meta)
    except llm_client.LlmError as exc:
        journal.schritt_protokollieren(
            lauf_id, "markt", "llm_lage", status="fehler", prompt=prompt,
            modell=modell, tokens=client.usage.total_tokens,
            dauer_s=round(_time.monotonic() - beginn, 1),
            detail={"fehler": str(exc)})
        log(f"  Markt-LLM fehlgeschlagen: {exc}")
        return None
    journal.schritt_protokollieren(
        lauf_id, "markt", "llm_lage", prompt=prompt, antwort=antwort,
        modell=modell, tokens=meta.get("total_tokens",
                                       client.usage.total_tokens) or 0,
        dauer_s=meta.get("dauer_s"), detail={"symbole": symbole})
    return antwort


def _code_lage(kennzahlen: dict) -> str:
    """Knappe maschinelle Fassung ohne LLM (Fallback, Code zitiert Zahlen)."""
    zeilen = []
    for symbol, k in kennzahlen.items():
        heute = (k.get("veraenderung_pct") or {}).get("heute")
        woche = (k.get("veraenderung_pct") or {}).get("7t")
        zeilen.append(f"{symbol}: Close {k.get('close')}"
                      + (f", heute {heute:+} %" if heute is not None else "")
                      + (f", 7 T {woche:+} %" if woche is not None else "")
                      + (f", ATR(H1) {k.get('atr14_h1')}" if k.get("atr14_h1") else ""))
    return "Marktlage (maschinelle Kurzfassung):\n" + "\n".join(zeilen)


def kontext_heute() -> dict | None:
    """Der neueste Marktkontext (für den Betreuer-Prompt); None = kein."""
    init_markt()
    from datetime import datetime, timedelta
    heute = datetime.now().date()
    with db._connect() as conn:
        rows = conn.execute(
            "SELECT ts, symbole_json, kennzahlen_json, lage_text "
            "FROM markt_kontext ORDER BY id DESC LIMIT 5").fetchall()
    for row in rows:
        try:
            if datetime.fromisoformat(row["ts"]).date() >= heute - timedelta(days=1):
                return {"ts": row["ts"],
                        "symbole": json.loads(row["symbole_json"] or "[]"),
                        "kennzahlen": json.loads(row["kennzahlen_json"] or "{}"),
                        "lage": row["lage_text"] or ""}
        except (ValueError, json.JSONDecodeError):
            continue
    return None
