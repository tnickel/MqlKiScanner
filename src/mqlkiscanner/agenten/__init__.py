# -*- coding: utf-8 -*-
"""Agentenbetrieb des MqlKiScanner (Bauplan doc/19_agentenbetrieb-bauplan.md).

Eigenständiger Daemon-Prozess im selben Projekt, der Engine und Datenbank
als Bibliothek nutzt. Phase A (Stand 22.09.2026): Dirigent-Tageslauf,
Journal/Protokoll, Lauf-Lock, Rollen-Konfiguration und UI-Anbindung.

Grundregeln (unverändert): Die Engine rechnet und bewertet — Agenten
beobachten, ordnen ein und melden. Jeder Schritt wird append-only
protokolliert; LLM-Aufrufe mit vollständigem Prompt und vollständiger
Antwort (kein Trockenmodus, Nutzer-Entscheidung 22.09.2026).

Bewusst OHNE Import der Untermodule: config.py zieht die Rollen-Defaults
aus .agenten.rollen — eine Import-Kette hier würde den Kreis schließen.
Untermodule werden explizit importiert (from mqlkiscanner.agenten import
journal, dirigent, ...).
"""
