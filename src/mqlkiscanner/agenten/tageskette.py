# -*- coding: utf-8 -*-
"""Komplettlauf der Tageskette — der ganze Agenten-Workflow in einem Aufruf.

Reihenfolge wie die Werktagskette des Schedulers (scheduler.faellige_rollen),
aber OHNE Takt-Prüfung — für den Ein-Knopf-Start auf der Agenten-Seite und
`--alles` auf der Kommandozeile:

  1. Ampelwechsel-Watcher (billig und idempotent — sieht auch Wechsel aus
     GUI-Scans)
  2. Dirigent    (Lagestatus + Tagesplan; nimmt das Lauf-Lock selbst)
  3. Markt       (MT5-Kurse nach der konfigurierten Start-Politik)
  4. Betreuer    (Export-Deltas gegen die Dossiers)
  5. Melder      (Tagesdigest ins Postfach)

Nicht Teil der Kette: Chefermittler (Sonntag/Monatsbericht) und autonome
Scans (Sonntag Teilscan / Monatserster Full) — sie bleiben an ihre Takte
gebunden bzw. laufen über die Scan-Seite oder CLI --scan. Eine fehlge-
schlagene oder übersprungene Rolle reißt die Kette nicht ab (wie im
Scheduler-Tick); das prozessübergreifende Lauf-Lock verhindert Doppel-Läufe
mit dem Daemon. Die Aktivschalter je Rolle (agenten_<rolle>_aktiv) werden
respektiert: Der Komplettlauf führt den Betrieb aus, wie er konfiguriert ist.
"""
from __future__ import annotations

from .. import config
from . import journal, lock, rollen

# Die Tageskette in Daemon-Reihenfolge (ohne Chef/Scan — siehe Modul-Doku).
KETTEN_ROLLEN: tuple[str, ...] = ("dirigent", "markt", "betreuer", "melder")


def kompakt_zusammenfassung(rolle_key: str, res: dict) -> str:
    """Einzeiler je Rolle aus den Keys, die der Lauf liefert (reiner Code)."""
    if res.get("resultat"):
        return str(res["resultat"])
    if res.get("zusammenfassung"):
        return str(res["zusammenfassung"])
    if rolle_key == "dirigent":
        plan = res.get("plan") or []
        return f"Plan: {', '.join(plan)}" if plan else ""
    if rolle_key == "markt":
        symbole = res.get("symbole") or []
        return f"{len(symbole)} Symbol(e) analysiert" if symbole else ""
    if res.get("meldung_id") is not None:
        return f"Meldung #{res['meldung_id']} im Postfach"
    return ""


def _rollen_name(rolle_key: str) -> str:
    rolle = rollen.ROLLEN_NACH_KEY.get(rolle_key)
    return rolle.name if rolle else rolle_key.capitalize()


def _rolle_ausfuehren(rolle_key: str, quelle: str, log, settings: dict) -> dict:
    """Eine Rolle der Kette ausführen — Lock-Disziplin wie beim Einzelstart
    aus der GUI (Dirigent nimmt das Lock intern und kurz, die übrigen halten
    es über die gesamte Laufdauer). Bei besetztem Lock gibt es — wie immer —
    einen dokumentierten Skip-Lauf statt eines stillen Doppel-Laufs."""
    from . import betreuer, dirigent, markt, melder  # spät: Kreisimporte

    if rolle_key == "dirigent":
        return dirigent.tageslauf(quelle=quelle, log=log)
    try:
        with lock.lauf_lock(config.DATA_DIR):
            if rolle_key == "markt":
                return markt.tageslauf(quelle=quelle, log=log, settings=settings)
            if rolle_key == "betreuer":
                return betreuer.tageslauf(quelle=quelle, log=log,
                                          settings=settings)
            return melder.tagesdigest(quelle=quelle, log=log, settings=settings)
    except lock.LockBesetzt as exc:
        lauf_id = journal.lauf_starten(rolle_key, quelle=quelle)
        pid_info = f" (PID {exc.pid})" if getattr(exc, "pid", None) else ""
        aktion = f"Komplettlauf: Startversuch {_rollen_name(rolle_key)}"
        resultat = (f"Übersprungen: Ein anderer Lauf{pid_info} war noch "
                    "aktiv (Kollisionsschutz).")
        journal.schritt_protokollieren(
            lauf_id, rolle_key, "lock", status="skipped",
            detail={"grund": str(exc), "pid": getattr(exc, "pid", None),
                    "alter_s": getattr(exc, "alter_s", None)})
        journal.lauf_abschliessen(lauf_id, "skipped",
                                  zusammenfassung=f"Lauf-Lock belegt: {exc}",
                                  aktion=aktion, resultat=resultat)
        return {"status": "skipped", "grund": str(exc)}


def tageskette(quelle: str = "gui", log=print, settings: dict | None = None,
               meldung=None) -> dict:
    """Die komplette Tageskette sofort ausführen.

    meldung(rolle_key, text, stand) ist ein optionaler Fortschritts-Kallback
    (stand: 'laeuft'|'ok'|'skipped'|'fehler') — die GUI speist damit ihren
    Status-Kasten, die CLI übergibt nichts. Rückgabe:
    {"status": ok|teilerfolg|fehler|skipped, "ergebnisse": [...],
     "zusammenfassung": "Dirigent: ok, Markt: ok, …"} — die Einzel-Läufe
    protokollieren sich selbst im Journal, die Kette ist nur Orchestrierung.
    """
    from . import melder, scheduler  # spät: Kreisimporte
    settings = settings if settings is not None else config.load_settings()
    journal.init_journal()
    ergebnisse: list[dict] = []

    def _notiz(rolle_key: str, text: str, stand: str) -> None:
        if meldung is not None:
            meldung(rolle_key, text, stand)

    # 1) Ampelwechsel-Watcher — vor der Kette, wie im Scheduler-Tick.
    _notiz("melder", "Ampelwechsel-Watcher prüfen …", "laeuft")
    try:
        wechsel = melder.pruefe_neue_wechsel(log=log)
        info = (f"{len(wechsel)} neue Ampelwechsel gemeldet" if wechsel
                else "keine neuen Ampelwechsel")
        ergebnisse.append({"rolle": "melder", "schritt": "wechsel_watcher",
                           "status": "ok", "info": info})
        _notiz("melder", f"Wechsel-Watcher: {info}", "ok")
    except Exception as exc:  # der Watcher darf die Kette nicht aufhalten
        ergebnisse.append({"rolle": "melder", "schritt": "wechsel_watcher",
                           "status": "fehler", "grund": str(exc)})
        _notiz("melder", f"Wechsel-Watcher fehlgeschlagen: {exc}", "fehler")
        log(f"Tageskette: Wechsel-Watcher fehlgeschlagen (weiter): {exc}")

    # 2) Die Rollen der Tageskette in Daemon-Reihenfolge.
    for rolle_key in KETTEN_ROLLEN:
        name = _rollen_name(rolle_key)
        if not scheduler.nicht_deaktiviert(settings, rolle_key):
            ergebnisse.append({"rolle": rolle_key, "status": "skipped",
                               "grund": f"Rolle {name} ist deaktiviert "
                                        "(Einstellungen → Agenten)."})
            _notiz(rolle_key, f"{name}: übersprungen — Rolle deaktiviert",
                   "skipped")
            continue
        _notiz(rolle_key, f"{name} läuft …", "laeuft")
        try:
            res = _rolle_ausfuehren(rolle_key, quelle, log, settings)
        except Exception as exc:  # eine Rolle darf die Kette nicht abreißen lassen
            ergebnisse.append({"rolle": rolle_key, "status": "fehler",
                               "grund": str(exc)})
            _notiz(rolle_key, f"{name}: Fehler — {exc}", "fehler")
            log(f"Tageskette: Rolle {rolle_key} fehlgeschlagen (weiter): {exc}")
            continue
        res = res if isinstance(res, dict) else {}
        status = str(res.get("status", "ok"))
        info = kompakt_zusammenfassung(rolle_key, res) or status
        ergebnisse.append({"rolle": rolle_key, "status": status, "info": info})
        if status == "fehler":
            _notiz(rolle_key, f"{name}: Fehler — {res.get('grund') or info}",
                   "fehler")
        elif status == "skipped":
            _notiz(rolle_key, f"{name}: übersprungen — {res.get('grund') or info}",
                   "skipped")
        else:
            _notiz(rolle_key, f"{name}: fertig — {info}", "ok")

    rollen_ergebnisse = [e for e in ergebnisse if not e.get("schritt")]
    fehler = sum(1 for e in rollen_ergebnisse if e["status"] == "fehler")
    ok = sum(1 for e in rollen_ergebnisse if e["status"] == "ok")
    if fehler == 0 and ok == 0:
        gesamt = "skipped"
    elif fehler == 0:
        gesamt = "ok"
    elif ok == 0:
        gesamt = "fehler"
    else:
        gesamt = "teilerfolg"
    teile = [f"{_rollen_name(e['rolle'])}: {e['status']}"
             for e in rollen_ergebnisse]
    zusammenfassung = (f"Komplettlauf: {ok} Rolle(n) ok"
                       + (f", {fehler} mit Fehler" if fehler else "")
                       + " — " + ", ".join(teile))
    return {"status": gesamt, "ergebnisse": ergebnisse,
            "zusammenfassung": zusammenfassung}
