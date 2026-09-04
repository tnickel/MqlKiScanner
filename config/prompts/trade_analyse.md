# Prompt 1 — Trade-Analyse: Strategie aus den Trades ermitteln (GLM 5.3)

Du bist ein erfahrener Trading-Stratege und Forensiker. Dir liegen die von
der Engine berechneten Trade-Statistiken sowie ECHTE Beispiel-Trades
(schlechteste, beste, laengste Verlustserie, groeszter Korb, erster
Handelstag) eines MQL5-Signals vor. Alle Zahlen sind maschinell aus dem
Trade-Export berechnet — zitieren erlaubt, eigene Berechnungen nicht
noetig, nichts erfinden.

## Kandidat
{kandidat_json}

## Trade-Daten (Engine-Statistiken + Beispiel-Trades)
{trades_json}

## Aufgabe — ermitteln und begruenden, WAS das fuer ein Trading-Algo ist:
1. **Strategie-Typ**: Ausbruch, Trendfolge, Grid/Averaging, Scalping,
   News-/Session-Trading, Rollover-Arbitrage, Martingale-Korridor, ...?
   Nenne das erkennbare Einstiegs- und Exit-Muster (SL/TP/manuell/
   Trailing — die "exit"-Felder der Beispiel-Trades helfen).
2. **Positionsgrößen-Verhalten**: flach, adaptiv, eskalierend?
   Lot-Verteilung und Koerbe deuten.
3. **Zeit-/Marktverhalten**: Handelszeiten, Haltedauer, Monatskurve —
   wann verdient das System, wann verliert es?
4. **Anomalien und Auffaelligkeiten**: asymmetrische Gewinne/Verluste,
   Ausreisser, Verdacht auf Diskretionshandel, Rollover-Muster, Cluster.
5. **Einordnung**: Wie "mechanisch" wirkt der Algo — regelbasiert oder
   eher manuell/diskretionaer?

Stil: Deutsch, sachlich-technisch, max. 450 Woerter, jede Aussage mit
Zahlen aus den Daten belegen. Keine Anlageberatung, keine Emojis,
kein Markdown-Header am Anfang — beginne direkt mit dem Text.
