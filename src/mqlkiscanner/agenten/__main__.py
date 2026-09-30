# -*- coding: utf-8 -*-
"""Einstiegspunkt des Agenten-Daemons: python -m mqlkiscanner.agenten

Ohne Argumente: Dauerschleife (Scheduler-Tick alle 30 s, Stopp über die
Steuerungstabelle). Argumente:
  --once     EINEN Dirigent-Tageslauf sofort ausführen (ohne Takt-Prüfung;
             ignoriert agenten_enabled — für Tests, Erstreundung und CLI)
  --markt    EINEN Marktbeobachter-Lauf sofort ausführen (Kursdaten aus dem
             MetaTrader, nur lesend; überspringt sauber, wenn das Terminal
             aus ist und der Selbststart nicht erlaubt wurde)
  --betreuer EINEN Betreuer-Tageslauf sofort ausführen (alle Kandidaten;
             Delta-Prüfung gegen die Dossiers, ignoriert agenten_enabled)
  --tick     EINEN Scheduler-Tick ausführen (mit Takt-Prüfung) und enden
  --alles    die KOMPLETTE Tageskette sofort ausführen (Ampelwechsel-Watcher
             → Dirigent → Markt → Betreuer → Tagesdigest; ohne Takt-Prüfung)
"""
from __future__ import annotations

import argparse
import logging

log = logging.getLogger("mqlkiscanner.agenten")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m mqlkiscanner.agenten",
        description="Agenten-Daemon des MqlKiScanner (Phasen A–E)")
    parser.add_argument("--once", action="store_true",
                        help="einen Dirigent-Tageslauf sofort ausführen")
    parser.add_argument("--markt", action="store_true",
                        help="einen Marktbeobachter-Lauf sofort ausführen")
    parser.add_argument("--betreuer", action="store_true",
                        help="einen Betreuer-Tageslauf sofort ausführen")
    parser.add_argument("--digest", action="store_true",
                        help="einen Tagesdigest des Melders sofort ausführen")
    parser.add_argument("--chef", action="store_true",
                        help="einen Lagebericht des Chefermittlers sofort ausführen")
    parser.add_argument("--scan", choices=["gelbgruen", "full"],
                        help="einen autonomen Scan sofort anstoßen (full: Katalog; "
                             "gelbgruen: nur 🟢/🟡 mit allen KI-Stufen)")
    parser.add_argument("--alles", action="store_true",
                        help="die komplette Tageskette sofort ausführen "
                             "(Watcher → Dirigent → Markt → Betreuer → Digest)")
    parser.add_argument("--tick", action="store_true",
                        help="einen Scheduler-Tick ausführen und enden")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from . import (betreuer, chef, dirigent, lock, markt, melder,
                   scan_launcher, scheduler, tageskette)
    from .. import config

    def _rolle_gezielt(rolle: str, fn):
        """B14 (Intensiv-Review 29./30.09.2026): Einzelrollen-Starts über
        die CLI nehmen denselben Rollen-Lock wie Daemon/Scheduler/Tages-
        kette — vorher konnte ein CLI-Start parallel zu GUI/Daemon
        doppelt exportieren (Doppel-Kosten, Doppel-Journal)."""
        try:
            with lock.lauf_lock(config.DATA_DIR, lock.rolle_lock_name(rolle)):
                return fn()
        except lock.LockBesetzt as exc:
            pid = getattr(exc, "pid", None)
            log.warning("%s läuft bereits (PID %s) — CLI-Start übersprungen "
                        "(Rollen-Lock).", rolle.capitalize(), pid)
            return None

    if args.once:
        ergebnis = _rolle_gezielt("dirigent", lambda: dirigent.tageslauf(
            quelle="cli", log=log.info))
        if ergebnis is not None:
            log.info("Ergebnis: %s", ergebnis.get("status"))
        return
    if args.markt:
        ergebnis = _rolle_gezielt("markt", lambda: markt.tageslauf(
            quelle="cli", log=log.info))
        if ergebnis is not None:
            log.info("Ergebnis: %s — %s", ergebnis["status"],
                     ergebnis.get("grund") or f"{len(ergebnis.get('kennzahlen', {}))} Symbole")
        return
    if args.betreuer:
        ergebnis = _rolle_gezielt("betreuer", lambda: betreuer.tageslauf(
            quelle="cli", log=log.info))
        if ergebnis is not None:
            log.info("Ergebnis: %s Signale — %s", ergebnis["signale"],
                     ergebnis["zusammenfassung"])
        return
    if args.digest:
        ergebnis = _rolle_gezielt("melder", lambda: melder.tagesdigest(
            quelle="cli", log=log.info))
        if ergebnis is not None:
            log.info("Ergebnis: %s — Meldung #%s", ergebnis["status"],
                     ergebnis.get("meldung_id", "-"))
        return
    if args.chef:
        ergebnis = _rolle_gezielt("chef", lambda: chef.lagebericht(
            quelle="cli", log=log.info))
        if ergebnis is not None:
            log.info("Ergebnis: %s — Meldung #%s", ergebnis["status"],
                     ergebnis.get("meldung_id", "-"))
        return
    if args.scan:
        ergebnis = scan_launcher.starte_scan(args.scan, quelle="cli",
                                             log=log.info)
        log.info("Ergebnis: %s — %s", ergebnis["status"],
                 ergebnis.get("zusammenfassung", ergebnis.get("grund", "")))
        return
    if args.alles:
        ergebnis = tageskette.tageskette(quelle="cli", log=log.info)
        log.info("Ergebnis: %s — %s", ergebnis["status"],
                 ergebnis["zusammenfassung"])
        return
    if args.tick:
        scheduler.tick(log=log.info)
        return
    scheduler.schleife(log=log.info)


if __name__ == "__main__":
    main()
