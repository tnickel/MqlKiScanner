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
