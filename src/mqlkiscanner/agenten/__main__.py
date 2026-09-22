# -*- coding: utf-8 -*-
"""Einstiegspunkt des Agenten-Daemons: python -m mqlkiscanner.agenten

Ohne Argumente: Dauerschleife (Scheduler-Tick alle 30 s, Stopp über die
Steuerungstabelle). Argumente:
  --once   EINEN Dirigent-Tageslauf sofort ausführen (ohne Takt-Prüfung;
           ignoriert agenten_enabled — für Tests, Erstreundung und CLI)
  --tick   EINEN Scheduler-Tick ausführen (mit Takt-Prüfung) und enden
"""
from __future__ import annotations

import argparse
import logging

log = logging.getLogger("mqlkiscanner.agenten")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m mqlkiscanner.agenten",
        description="Agenten-Daemon des MqlKiScanner (Phase A: Dirigent)")
    parser.add_argument("--once", action="store_true",
                        help="einen Dirigent-Tageslauf sofort ausführen")
    parser.add_argument("--tick", action="store_true",
                        help="einen Scheduler-Tick ausführen und enden")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from . import dirigent, scheduler

    if args.once:
        ergebnis = dirigent.tageslauf(quelle="cli", log=log.info)
        log.info("Ergebnis: %s", ergebnis.get("status"))
        return
    if args.tick:
        scheduler.tick(log=log.info)
        return
    scheduler.schleife(log=log.info)


if __name__ == "__main__":
    main()
