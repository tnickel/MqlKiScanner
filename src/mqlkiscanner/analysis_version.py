"""Version der fachlichen Bewertung, unabhängig vom SQLite-Tabellenschema.

Bei Änderungen an Pflichtprüfungen oder Bewertungsregeln erhöhen: Live-Befunde
älterer Versionen müssen neu geprüft werden. Laufarchive bleiben unverändert.
"""

# 12 (05.10.2026, Nutzer-Regel): Max-Drawdown auf der REALEN Kontokurve —
# Ein-/Auszahlungen bleiben in Kurve und Peak (Auszahlungen erzeugen keinen
# Drawdown, Peak-Anpassung); implizite Kapitalbasis (Web-Balance − Netto)
# entfällt, Fallback 10k virtuell markiert. Alter Bestand: neu scannen.
# 13 (05.10.2026 spaet, Copilot-Review): Zeitgenauer TWR-Zaehler bei
# Kapitalfluessen (vorher Monatsanfang: Gewinnauszahlung blaehte die Rendite
# auf), exakte Zeitspanne im TWR-Zweig, Mindesthistorie 3 Monate +
# Calmar-Gate (f273287). Bestand ohne Status historie_zu_kurz/TWR waere
# sonst als aktuell durchgegangen (10-Tage-Altdatensatz -> Gruen).
# Alter Bestand: neu scannen.
# 14 (05.10.2026 nachts, Nutzer-Fall KiraCat): Auszahlungen in Stunden ohne
# vollstaendige Kurse (kein Messpunkt) wurden in der Equity-Rekonstruktion
# verworfen — der Peak blieb stehen und die Auszahlung zaehlte als Drawdown.
# Jetzt am naechsten Messpunkt gebucht. Alter Bestand: neu scannen.
FORENSICS_VERSION = 14
