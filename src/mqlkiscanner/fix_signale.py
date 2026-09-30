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

SETTINGS_KEY = "fix_signal_ids"


def fix_ids(settings: dict | None = None) -> set[int]:
    """Gesetzte Fix-IDs aus den Einstellungen (robust gegen Muell-Eintraege)."""
    settings = settings if settings is not None else config.load_settings()
    ids: set[int] = set()
    for raw in settings.get(SETTINGS_KEY) or []:
        try:
            ids.add(int(raw))
        except (TypeError, ValueError):
            continue
    return ids


def setzen(signal_id: int, fix: bool = True) -> None:
    """Fix-ID dauerhaft setzen/entfernen (persistiert in app_settings.json)."""
    signal_id = int(signal_id)
    settings = config.load_settings()
    ids = fix_ids(settings)
    if fix:
        ids.add(signal_id)
    else:
        ids.discard(signal_id)
    settings[SETTINGS_KEY] = sorted(ids)
    config.save_settings(settings)


def ordne_fix_vorne(cands: list[dict], settings: dict | None = None) -> tuple[list[dict], list[dict]]:
    """Trennt Fix-Kandidaten ab, damit sie die top_n_export-Grenze nie trifft.

    Aufrufer setzt die Reihenfolge zusammen: fix_vorne + rest, danach erst
    die Begrenzung. Ohne Trennung koennte eine Fix-ID hinter Platz 30 der
    Abonnenten-Sortierung liegen und trotzdem uebersprungen werden.
    """
    fix = fix_ids(settings)
    vorne = [c for c in cands if c.get("id") in fix]
    rest = [c for c in cands if c.get("id") not in fix]
    return vorne, rest


def waehle_fuer_export(cands: list[dict], top_n: int,
                       settings: dict | None = None) -> tuple[list[dict], list[dict]]:
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
    [{quelle, angeboten, genommen}] für das Log.
    """
    fix_vorne, rest = ordne_fix_vorne(cands, settings)
    ausgeschlossen = {e.get("id") for e in
                      config.load_known_signals().get("ausgeschlossen", [])}
    rest_mit_ausschluss = [c for c in rest if c.get("id") in ausgeschlossen]
    rest = [c for c in rest if c.get("id") not in ausgeschlossen]
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
    for k in reihenfolge:
        gruppe = sorted(gruppen[k],
                        key=lambda c: -(float(c.get("abonnenten") or 0)))
        genommen = gruppe[:limit]
        auswahl.extend(genommen)
        infos.append({"quelle": k, "angeboten": len(gruppe),
                      "genommen": len(genommen)})
    if rest_mit_ausschluss:
        infos.append({"quelle": "ausschlussliste",
                      "angeboten": len(rest_mit_ausschluss),
                      "genommen": 0})
    return auswahl, infos


def teilscan_ziel_ids(alt_ergebnisse, settings: dict | None = None) -> set[int]:
    """Teilscan-Scope: 🟢/🟡 laut DB-Stand PLUS alle Fix-IDs.

    Fix-IDs sollen immer geprueft werden — auch wenn ihre aktuelle Ampel
    gerade 🔴/⛔/⚪ ist (z. B. veraltete Forensik): sonst wuerde ein
    gepinntes Signal genau dann nicht mehr beobachtet, wenn man es am
    dringendsten neu bewerten muesste. Dafuer gilt die Live-Einschraenkung
    (keine Demo-/CSV-Zeilen) weiter.
    """
    ids = {r.id for r in alt_ergebnisse
           if r.ampel in ("🟢", "🟡")
           and getattr(r, "source_kind", "live") == "live"}
    return ids | fix_ids(settings)
