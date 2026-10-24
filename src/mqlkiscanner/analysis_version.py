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
# vollständige Kurse (kein Messpunkt) wurden in der Equity-Rekonstruktion
# verworfen — der Peak blieb stehen und die Auszahlung zaehlte als Drawdown.
# Jetzt am naechsten Messpunkt gebucht. Alter Bestand: neu scannen.
# 15 (08.10.2026, Arbeitsliste „47 Symbole ohne Kontrakt“): Broker-Fallback
# für Quellen-Signale repariert — RoboMonitor antwortet mit version mql4/
# mql5 (nie 'robo'), CopyFX-Signale hatten deshalb broker_server=None und
# alle broker-gebundenen Kontraktspecs (AAPL=100, .JP225CASH=100 JPY, WTI
# =1000 Barrel, ES-Future 50 USD/Punkt …) griffen nicht. Jetzt greift
# zusätzlich das Quellen-Kürzel (robo→RoboForex). Schock-/Equity-Werte der
# Quellen-Signale ändern sich dadurch. Alter Bestand: neu scannen.
# 16: Separate Charge/Commission-Buchungen belasten alle Ergebnis- und
# Kontokurven; niemals als externer Flow neutralisieren. Neu scannen.
# 17: Teilmessung erhält bekannte Floatings, Flow-Rendite wird ohne belegte
# Preflow-Equity nicht als Equity-TWR freigegeben, Roh-DD/Kosten/FX korrigiert.
# 18: Direkte MQL-Kontobeträge benötigen belegtes USD; native Fremdwährung
# darf nicht als USD-Basis für H1-/Schockmessung wiederverwendet werden.
# 19: Auch MQL-Quelltrades sind native Kontobeträge; kein pauschaler USD-
# Vertrag durch REST-Transport. Nur belegtes USD darf in die USD-Forensik.
# 20: Exakt belegte Vantage-FT-Kontrakte GER40ft/UK100ft verwenden native
# EUR-/GBP-Gewinnwaehrung samt historischer USD-Umrechnung. Die bisherigen
# festen USD-Medianfaktoren und ungebundenen Parallelmodelle entfallen.
# 21: Exakt belegte Vantage-Kontrakte Nikkei225 (JPY) und Soybean-C (USD),
# historische CNH-/ETH-Umrechnung im Exposure nur mit geschlossenem H1-Bar,
# belegter Tradezeit und identischem Terminal-/Serverfeed. Kein CNH=CNY.
# 22: One shared capital decision for drawdown/exposure/equity. Prefer proven
# starting capital; otherwise retain an explicit complex model estimate with
# provenance/uncertainty. Model percentages never authorize automatic green.
# Old capital-dependent evidence stays archived and stale until an explicit run.
FORENSICS_VERSION = 22
