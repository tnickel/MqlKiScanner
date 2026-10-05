# Max-Drawdown auf der REALEN Kontokurve — Ein-/Auszahlungen bleiben drin (Nutzer-Regel 05.10.2026)

## Die neue Regel (ersetzt die kapitalflussneutrale DD-Messung als HAUPTWert)

1. **DD-Kurve = reale Kontokurve inkl. Flows:** Einzahlungen heben die Kurve (und den Peak — der Betreiber erhöht danach seine Lots, also wachsen die Drawdowns; genau das erlebt ein Kopierer). **Auszahlungen erzeugen KEINEN Drawdown**: der laufende Peak wird bei einer Auszahlung um den Betrag gesenkt (nie unter den aktuellen Stand) — Geld, das das Konto verlässt, ist kein Verlust (Standard-Hochwassermark-Methode mit Flow-Anpassung).
2. **Basis = das echte Kapital des Betreibers:** CSV-Einzahlungen im Export (gewinnen immer, in `drawdown.run`) → Signalseite „Initial Deposit" → sonst **10.000 USD virtuell, deutlich markiert** (existentes Label „Kapitalbasis virtuell").
3. **Implizite Basis (Web-Balance − Trade-Netto, B3) ENTFÄLLT:** Sie ist mit Flows-in-der-Kurve mathematisch falsch (zählt Flows als Startkapital — der LadyTrader1-Fehler: 41.577 statt 9.000). Folge: Quellen-Signale ohne Initial Deposit und ohne Balance-Rows (Pelikan/Vantage/Zulu) fallen auf 10k virtuell mit Markierung; Lexo/Pentagon/AIT-DD% wachsen dadurch Richtung Realität (RetDD bleibt davon nahezu unberührt, da Ertrag und DD auf demselben Nenner stehen).

## Umsetzungsschritte

1. **`forensics/drawdown.py`** — `trading_dd` wird auf die reale Kurve gestellt: Ereignisse = Trades (netto) + Balance-Rows chronologisch, Peak-Verfolgung mit Auszahlungs-Anpassung; zusätzlich Feld `trading_dd_virtuell` (bisherige Kurve, bleibt Diagnostik/Plattform-Abgleich) und `kurve: "real_mit_flows" | "virtuell_ohne_flows"`. Signale ohne Balance-Rows: identisch zu heute (kein Verhaltenbruch).
2. **`forensics/equity_rekonstruktion.py` + `equity_studie.py`** — Kurs-Max-DD (floating-inklusive) reitet künftig auf der realen Kurve: `startkapital + realisiert + Σ Flows bis t + floating`, Peak-Anpassung bei Auszahlungen; Methodik-/`kapitalfluesse`-Strings ehrlich umgeschrieben. **FORENSICS_VERSION → 12** (erzwingt Bestands-Neuberechnung). Die Karte „Konto-DD (kapitalflussneutral)" + Kopier-Simulation bleiben als Vergleich bestehen (rendite_index-Modell für „mein 10k-Konto" ist dafür weiterhin richtig).
3. **`pipeline.py`** — Kaskade auf Signalseite → virtuell gekürzt (`_implizite_kapitalbasis` entfernen), `_kennezeichne_virtuelle_kapitalbasis` ohne Implizit-Zweig, `_kapitalbasis_abgleich`-Skip-Liste bereinigen, Forensik-JSON/Urteile nennen die neue Kurvenbasis; Ertrag/effizienz_kennzahlen wie gehabt auf der verwendeten Basis (Zähler netto bleibt flow-neutral).
4. **`signal_statistik.py`** — dieselbe Kaskade; Chart-Kurve des Alle-Signale-Details wird die reale Kontokurve (Flows als Sprünge sichtbar); `BASIS_KUERZEL`/Langtexte ohne „implizit".
5. **`forensics/exposure.py`** — Konto-Verlauf beim Schock-Peak inkl. Flows bis dahin (konsistente Prozentbasis).
6. **Texte synchron** (B12-Regel!): `llm/prompts.py` + eingebaute Defaults (Methodik-Beschreibungen „reale Kontokurve inkl. Ein-/Auszahlungen; Auszahlungen erzeugen keinen Drawdown"), Ampel-Matrix-Kriterientext, UI-Hilfen (app_ui, equity_studie_ui, help_content).
7. **Tests:** B3-Tests entfernen/umschreiben (Regeländerung dokumentiert im Code-Kommentar), NEU: Flow-DD-Tests (Einzahlung hebt Peak → folgender Verlust zählt voll; Auszahlung erzeugt keinen fake-DD — LadyTrader-Szenario 9k → Flows → −53k-Abhebung), Kaskaden-Tests (Seite→virtuell), Reko-/Studien-Tests mit Flows, Prompt-Sync-Test, betroffene Fixtures anpassen.
8. **`scripts/verify_engine.py`** — Cent-Anker mit neuer Kurve neu kalibrieren (dokumentiert, mit Plattform-Gegenwert).
9. **AGENTS.md** (Regel-Eintrag ersetzt B3-Nachfolge; Verweis auf Nutzer-Entscheid 05.10.), Memory-Update; Commit + Push. Danach **Bestands-Re-Scan** (Version 12 macht alle alten Befunde „veraltet").

## Bewusste Grenzen
- Ohne Balance-Rows (MT5/Pelikan/Vantage/Zulu-Exporte) bleibt die Kurve zwangsläufig virtuell — klar markiert statt schöngerechnet.
- RetDD-Regel unverändert: Nenner weiterhin nur die floating-inklusive Kursmessung (jetzt auf realer Kurve), Monitor-DD bleibt Closing-Untergrenze.