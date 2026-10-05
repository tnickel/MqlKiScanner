"""Version der fachlichen Bewertung, unabhängig vom SQLite-Tabellenschema.

Bei Änderungen an Pflichtprüfungen oder Bewertungsregeln erhöhen: Live-Befunde
älterer Versionen müssen neu geprüft werden. Laufarchive bleiben unverändert.
"""

# 12 (05.10.2026, Nutzer-Regel): Max-Drawdown auf der REALEN Kontokurve —
# Ein-/Auszahlungen bleiben in Kurve und Peak (Auszahlungen erzeugen keinen
# Drawdown, Peak-Anpassung); implizite Kapitalbasis (Web-Balance − Netto)
# entfällt, Fallback 10k virtuell markiert. Alter Bestand: neu scannen.
FORENSICS_VERSION = 12
