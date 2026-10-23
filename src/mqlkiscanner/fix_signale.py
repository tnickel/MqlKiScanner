# -*- coding: utf-8 -*-
"""Fix-IDs: Signal-IDs, die JEDEN Scan durchlaufen (Nutzer-Wunsch 28.09.2026).

Grund: Der Scanner holt seine Kandidaten aus den MQL5-Top-Listen (2 Seiten
je Plattform) und filtert danach nach Wochen und Abonnenten. Ein fest
beobachtetes Signal — z. B. die Empfehlung KiraCat — fällt aus dieser
Menge heraus, sobald es in den Listen abrutscht oder den Vorfilter nicht
mehr besteht; der 27.09.2026 zeigte genau diese Lücke. Fix-IDs umgehen
beides: Sie werden notfalls einzeln von ihrer Signalseite geladen,
ueberspringen den Vorfilter und stehen in der Export-Auswahl
(top_n_export) immer vorne. Im Teilscan sind sie zusaetzlich immer im
Scope, auch wenn ihre aktuelle Ampel nicht 🟢/🟡 ist.

"Fix" ist eine Scan-Zusage, kein Vorzugsurteil: Ampel, Score und Urteil
gelten fuer Fix-IDs exakt wie fuer alle anderen Signale.
"""
from __future__ import annotations

from . import config
from .signal_identity import key_for, AmbiguousSignalIdentity

SETTINGS_KEY = "fix_signal_ids"


def fix_ids(settings: dict | None = None) -> set[int]:
    """Gesetzte Fix-IDs aus den Einstellungen (robust gegen Muell-Eintraege)."""
    include_db = settings is None
    settings = settings if settings is not None else config.load_settings()
    ids: set[int] = set()
    for raw in settings.get(SETTINGS_KEY) or []:
        try:
            ids.add(int(raw))
        except (TypeError, ValueError):
            continue
    if include_db:
        from . import db
        ids.update(db.list_signal_fixierungen())
    return ids


def fix_keys(settings: dict | None = None) -> set[tuple[str, int]]:
    """Resolve old pins only when their owner is unambiguous; new pins use refs."""
    from . import db
    settings = settings if settings is not None else config.load_settings()
    keys = set(db.list_signal_fixierungen(identitaeten=True))
    for sid in fix_ids(settings):
        try:
            identity = db.resolve_identity(sid)
        except AmbiguousSignalIdentity:
            continue
        if identity is not None:
            keys.add(identity.signal_key)
    return keys


def ist_fix(signal, settings: dict | None = None) -> bool:
    return key_for(signal) in fix_keys(settings)


def unaufgeloeste_fix_ids(settings: dict | None = None) -> set[int]:
    """Legacy settings need explicit reassignment if their owner is unproven."""
    from . import db
    settings = settings if settings is not None else config.load_settings()
    unresolved = set()
    for sid in fix_ids(settings):
        try:
            if db.resolve_identity(sid) is None:
                unresolved.add(sid)
        except AmbiguousSignalIdentity:
            unresolved.add(sid)
    return unresolved


def setzen(signal_id: int, fix: bool = True, *, quelle: str = "mql5") -> None:
    """Fix-ID dauerhaft setzen/entfernen (persistiert in app_settings.json)."""
    signal_id = int(signal_id)
    settings = config.load_settings()
    from . import db
    db.set_signal_fix(signal_id, fix, quelle=quelle)
    # Consume legacy entries at the explicit user assignment. Never write new
    # source-less pins: the connection's stable namespace owns the DB pin.
    ids = fix_ids(settings)
    ids.discard(signal_id)
    settings[SETTINGS_KEY] = sorted(ids)
    config.save_settings(settings)


def ordne_fix_vorne(cands: list[dict], settings: dict | None = None) -> tuple[list[dict], list[dict]]:
    """Trennt Fix-Kandidaten ab, damit sie die top_n_export-Grenze nie trifft.

    Aufrufer setzt die Reihenfolge zusammen: fix_vorne + rest, danach erst
    die Begrenzung. Ohne Trennung koennte eine Fix-ID hinter Platz 30 der
    Abonnenten-Sortierung liegen und trotzdem uebersprungen werden.
    """
    fix = fix_keys(settings)
    vorne = [c for c in cands if key_for(c) in fix]
    rest = [c for c in cands if key_for(c) not in fix]
    return vorne, rest


def begruendungseintrag(c: dict, status: str, grund: str) -> dict:
    """Einheitlicher Erklärungs-Datensatz je Signal (Nutzer-Wunsch 02.10.:
    jede Filter-Entscheidung nachvollziehbar). `url` ist die Signal-URL,
    soweit die Quelle eine liefert (mql5/Vantage ja, Pelican nur Plattform-Root).
    """
    return {"id": c.get("id"), "name": c.get("name") or "",
            "quelle": c.get("quelle_kuerzel") or "mql5",
            "wochen": c.get("wochen"),
            "abonnenten": c.get("abonnenten"),
            "url": c.get("url") or "",
            "status": status, "grund": grund}


def begruendung_upsert(begruendung: list[dict], eintrag: dict) -> None:
    """Eintrag einfügen ODER vorhandenen (gleiche Quelle + ID) ersetzen.

    Ohne Upsert stünde ein Signal doppelt in der Liste, sobald der Vorfilter
    es als KANDIDAT vermerkt hat und die Slot-/Scope-Entscheidung danach
    den Status präzisiert (konkreter Fall 02.10.: 974 Zeilen, davon 20 doppelt).
    """
    key = (eintrag.get("quelle"), eintrag.get("id"))
    for i, alt in enumerate(begruendung):
        if (alt.get("quelle"), alt.get("id")) == key:
            neu = dict(alt)
            neu.update(eintrag)
            begruendung[i] = neu
            return
    begruendung.append(eintrag)


def waehle_fuer_export(cands: list[dict], top_n: int,
                       settings: dict | None = None,
                       begruendung: list[dict] | None = None,
                       modus: str = "full"
                       ) -> tuple[list[dict], list[dict]]:
    """Auswahl für die Forensik (Nutzer-Wunsch 29.09.: „30 von jedem").

    - Fix-IDs zuerst — die Grenze trifft sie nie, und sie verbrauchen
      KEINE Quellen-Slots mehr (vorher: fix_vorne + rest[:top_n]).
    - Danach JE DATENQUELLE die top_n abonnentenstärksten Kandidaten —
      eine große Quelle (2223 MQL5-Signale) verdrängt eine kleine
      (Pelican) nicht mehr aus der Prüfung. Kandidaten ohne
      quelle_kuerzel zählen als „mql5" (Crawler-Weg).
    - B7 (Intensiv-Review 29./30.09.2026): Ausschlüsse (known_signals,
      ⛔) belegen KEINE Slots mehr und verbrauchen keine Forensik/KI —
      im Ziellauf hielten 13 ⛔ 43 % der MQL5-Slots und ~400k Tokens
      gebunden, während 12 normale Kandidaten ungeprüft blieben. Wer ein
      ⛔ trotzdem beobachten will, pinned es als Fix-ID (bewusste Wahl).

    Rückgabe (auswahl, infos): auswahl = finale Reihenfolge; infos =
    [{quelle, angeboten, genommen}] für das Log. `modus` steuert nur den
    Begründungs-Text: "full" erklärt die Slot-Ränge, "gelbgruen" den
    Teilscan-Scope (dort sind die Kandidaten vorab schon auf 🟢/🟡/Fix
    gefiltert — Ränge spielen dann keine Rolle).
    """
    fix_vorne, rest = ordne_fix_vorne(cands, settings)
    ausgeschlossen = {key_for(e) for e in
                      config.load_known_signals().get("ausgeschlossen", [])}
    rest_mit_ausschluss = [c for c in rest if key_for(c) in ausgeschlossen]
    rest = [c for c in rest if key_for(c) not in ausgeschlossen]
    gruppen: dict[str, list[dict]] = {}
    reihenfolge: list[str] = []
    for c in rest:
        k = str(c.get("quelle_kuerzel") or "mql5")
        if k not in gruppen:
            gruppen[k] = []
            reihenfolge.append(k)
        gruppen[k].append(c)
    auswahl = list(fix_vorne)
    infos = []
    limit = max(0, int(top_n or 0))
    teilscan = modus == "gelbgruen"

    def _slot_grund(c: dict, rang: int, genommen_: bool) -> dict:
        if teilscan:
            # B12 (Lauf-Review 02.10.): Auch im Teilscan zählt die Slot-
            # Grenze — eine Quelle mit mehr Scope-Kandidaten als Slots
            # darf Überzählige nicht als „wird geprüft" beschreiben.
            if genommen_:
                grund = ("✓ Im Teilscan-Scope: aktuell 🟢/🟡 laut letztem Lauf "
                         "— wird geprüft (Rang " + str(rang) + " je Quelle spielte "
                         "keine Rolle, alle Quellen-Slots reichten).")
                status = "AUSGEWAEHLT"
            else:
                grund = ("✗ Im Teilscan-Scope (🟢/🟡), aber Rang " + str(rang) +
                         " in Quelle " + k + " hinter der Slot-Grenze (Top " +
                         str(limit) + " je Quelle) — nicht geprüft.")
                status = "OHNE_SLOT"
        elif genommen_:
            grund = (f"✓ Ausgewählt: Rang {rang} in Quelle {k} "
                     f"(Abonnenten-absteigend, Top {limit} je Quelle).")
            status = "AUSGEWAEHLT"
        else:
            grund = (f"✗ Nicht ausgewählt: Rang {rang} in Quelle {k} — "
                     f"nur die Top {limit} je Quelle kommen in die "
                     "Forensik (Abonnenten-Rang).")
            status = "OHNE_SLOT"
        return begruendungseintrag(c, status, grund)

    for k in reihenfolge:
        gruppe = sorted(gruppen[k],
                        key=lambda c: (-(float(c.get("abonnenten") or 0)), int(c["id"])))
        genommen_ids = {c.get("id") for c in gruppe[:limit]}
        if begruendung is not None:
            for rang, c in enumerate(gruppe, 1):
                begruendung_upsert(
                    begruendung, _slot_grund(c, rang, c.get("id") in genommen_ids))
        genommen = gruppe[:limit]
        auswahl.extend(genommen)
        infos.append({"quelle": k, "angeboten": len(gruppe),
                      "genommen": len(genommen)})
    if rest_mit_ausschluss:
        infos.append({"quelle": "ausschlussliste",
                      "angeboten": len(rest_mit_ausschluss),
                      "genommen": 0})
        if begruendung is not None:
            for c in rest_mit_ausschluss:
                begruendung_upsert(begruendung, begruendungseintrag(
                    c, "AUSGESCHLOSSEN",
                    "⛔ Steht auf der Ausschlussliste (known_signals.json) — "
                    "belegt keinen Slot und kein KI-Budget (B7). "
                    "Bei Bedarf als Fix-ID pinnen."))
    return auswahl, infos


def begruende_teilscan_scope(begruendung: list[dict] | None, cands: list[dict],
                             ziel_ids: set[int], alt_ergebnisse) -> None:
    """Teilscan-Filter erklären (Nutzer-Wunsch 02.10.: die Sprünge
    974 → Kandidaten → geprüfte müssen je Signal begründet sein).

    Für jeden Kandidaten, der NICHT im Teilscan-Scope ist, wird der
    KANDIDAT-Eintrag zu NICHT_IM_SCOPE präzisiert — mit dem Ampel-Stand
    aus der DB, der die Entscheidung getragen hat. Noch nie bewertete
    Signale werden genauso ehrlich benannt.
    """
    if begruendung is None:
        return
    ampeln = {key_for(r): getattr(r, "ampel", None) for r in alt_ergebnisse}
    namen = {key_for(r): getattr(r, "name", "") or "" for r in alt_ergebnisse}
    for c in cands:
        if key_for(c) in ziel_ids:
            continue
        ampel = ampeln.get(key_for(c))
        if ampel is None:
            grund = ("✗ Teilscan: noch nie bewertet (kein DB-Eintrag) — "
                     "geprüft werden nur aktuell 🟢/🟡 laut Datenbank "
                     "plus Fix-IDs. Der nächste Full-Scan bewertet neu.")
        else:
            grund = (f"✗ Teilscan: letztes Urteil {ampel or '⚪'} — geprüft "
                     "werden nur aktuell 🟢/🟡 laut Datenbank plus Fix-IDs.")
        eintrag = begruendungseintrag(c, "NICHT_IM_SCOPE", grund)
        # Namens-/Ampel-Stand aus der DB ist aktueller als der Katalog
        db_name = namen.get(key_for(c))
        if db_name:
            eintrag["name"] = db_name
        begruendung_upsert(begruendung, eintrag)


def teilscan_ziel_keys(alt_ergebnisse, settings: dict | None = None) -> set[tuple[str, int]]:
    """Teilscan-Scope: 🟢/🟡, deren fehlgeschlagene Wiederholungen und Fix-IDs.

    Fix-IDs sollen immer geprueft werden — auch wenn ihre aktuelle Ampel
    gerade 🔴/⛔/⚪ ist (z. B. veraltete Forensik): sonst wuerde ein
    gepinntes Signal genau dann nicht mehr beobachtet, wenn man es am
    dringendsten neu bewerten muesste. Dafuer gilt die Live-Einschraenkung
    (keine Demo-/CSV-Zeilen) weiter.
    """
    from . import db
    ids = set()
    for r in alt_ergebnisse:
        if getattr(r, "source_kind", "live") != "live":
            continue
        eligible = r.ampel in ("🟢", "🟡")
        if r.ampel == "⚪" and getattr(r, "fehler", ""):
            # Failed attempts deliberately do not append an evaluation to the
            # colour history. Retry the last successful eligible evaluation,
            # without upgrading the current failed result or admitting every
            # white / never-scanned entry to the partial scan.
            previous = db.get_last_ampel_verlauf(r.id, quelle=key_for(r)[0]) or {}
            eligible = previous.get("ampel") in ("🟢", "🟡")
        if eligible:
            ids.add(key_for(r))
    return ids | fix_keys(settings)


def teilscan_ziel_ids(alt_ergebnisse, settings: dict | None = None) -> set[int]:
    """Legacy projection: omit IDs whose ownership is ambiguous."""
    keys = teilscan_ziel_keys(alt_ergebnisse, settings)
    owners: dict[int, set[str]] = {}
    for r in alt_ergebnisse:
        source, sid = key_for(r)
        owners.setdefault(sid, set()).add(source)
    return {sid for source, sid in keys if len(owners.get(sid, {source})) == 1}


def teilscan_ergaenze_aus_db(ziel_ids: set[int], vorhanden_ids: set[int],
                             settings: dict | None = None,
                             begruendung: list[dict] | None = None) -> list[dict]:
    """Teilscan-Vertrag („nur 🟢/🟡 laut DB") auch bei OFFLINE-Quelle erfüllen.

    Nutzer-Fall 02.10.2026: 12 pelik-🟡 waren laut DB im Teilscan-Scope,
    aber die Quelle antwortete nicht → sie fehlten im Crawl → sie wurden
    still übersprungen. Diese Ergänzung baut Kandidaten aus dem DB-Stand
    (ScanResult → Kandidaten-Format); die Forensik nutzt dann die
    gecachten Metrics/Trades-Artefakte (ingest-Offline-Fallback).

    Nur Quellen-Signale (quelle != mql5) werden ergänzt — MQL5-Direkt-
    Signale brauchen die Kennzahlen-Seite live (mql5.com) und werden vom
    Fix-ID-Mechanismus bzw. dem Crawl abgedeckt.
    """
    if not ziel_ids:
        return []
    fehlen = ziel_ids - vorhanden_ids
    if not fehlen:
        return []
    from . import db as _db  # spät: kein Kreisimport
    from .pipeline import results_from_db  # spät: kein Kreisimport
    quellen_nach_kuerzel = {}
    for q in _db.list_quellen(nur_aktiv=True):
        quellen_nach_kuerzel.setdefault(_db.kanonische_quelle(q["kuerzel"]), q)
    ergaenzungen: list[dict] = []
    for r in results_from_db(settings):
        if key_for(r) not in fehlen or r.quelle == "mql5":
            continue
        q = quellen_nach_kuerzel.get(r.quelle)
        if q is None:
            continue
        version = (r.platform or "mql5").lower()
        ergaenzungen.append({
            "id": r.id,
            "name": r.name,
            "platform": r.platform or "",
            "url": r.url or "",
            "abonnenten": r.abonnenten,
            "wochen": r.wochen,
            "quelle_kuerzel": r.quelle,
            "quelle_id": q["id"],
            "quellen_uid": q.get("quellen_uid") or "",
            "signal_ref": r.signal_ref,
            "quelle_version": version,
        })
        if begruendung is not None:
            begruendung_upsert(begruendung, {
                "id": r.id, "name": r.name, "quelle": r.quelle,
                "wochen": r.wochen, "abonnenten": r.abonnenten,
                "url": r.url or "", "status": "AUSGEWAEHLT",
                "grund": (f"✓ Im Teilscan-Scope ({r.ampel}) — Quelle offline, "
                          "aus dem DB-Stand ergänzt; Forensik lief aus den "
                          "gecachten Trade-/Metrics-Artefakten.")})
    # A pin may originate in the complete catalog before any workflow scan.
    # Such entries have a registry identity but deliberately no signals head.
    # Supplement them without creating a workflow row or inventing an MQL URL.
    ergaenzt = {key_for(c) for c in ergaenzungen}
    for row in _db.katalog_list():
        key = key_for(row)
        if key not in fehlen or key in ergaenzt or key[0] == "mql5":
            continue
        q = quellen_nach_kuerzel.get(key[0])
        if q is None or row.get("quellen_uid") != q.get("quellen_uid"):
            continue
        c = {"id": key[1], "name": row.get("name") or str(key[1]),
             "platform": row.get("platform") or "", "url": row.get("url") or "",
             "abonnenten": row.get("abonnenten"), "wochen": row.get("wochen"),
             "quelle_kuerzel": key[0], "quelle_id": q["id"],
             "quellen_uid": row.get("quellen_uid"), "signal_ref": row.get("signal_ref"),
             "quelle_version": row.get("version") or ""}
        ergaenzungen.append(c)
        ergaenzt.add(key)
        if begruendung is not None:
            begruendung_upsert(begruendung, begruendungseintrag(
                c, "AUSGEWAEHLT", "📌 Fix-Signal aus dem vollständigen Quellenkatalog ergänzt."))
    return ergaenzungen
