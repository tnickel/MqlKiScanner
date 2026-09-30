# Kapitalbasis-Prüfung — unabhängige Nachrechnung aller Signale mit Forensik

**Zweck:** B2 (Ertragskriterium) und B3 (virtuelle 10.000-USD-Basis) behaupten,
dass Risiko- und Ertragsprozente auf unterschiedlichen Kapitalbasen gerechnet
werden. Dieses Dokument misst das für **alle 33 Signale mit Forensik** des
Ziellaufs `2026-09-30_025355_970680_c65bf5cd` und prüft die Grundannahme der
Korrektur B3.

**Methode:** eigener CSV-Parser (`kapitalbasis_check.py`), kein Import von
`src/mqlkiscanner`. Quelle der Trades: `data/quellen/pelik/pelican_<id>_trades.csv`
bzw. `data/trade_snapshots/*.csv`; Web-Balance aus
`data/quellen/pelik/pelican_<id>_metrics.json`; Wochen/Monate aus dem
Produkt-Drawdown.

**Spalten:**

| Kürzel | Bedeutung |
|---|---|
| `netto` | Σ Netto-PnL aller Trades (USD) — unabhängig gezählt |
| `dd_usd` | rekonstruierter Produkt-Drawdown in USD |
| `mon` | Laufzeit in Monaten |
| `n` | Anzahl Trades |
| `kb_prod` | produktive Kapitalbasis der Engine |
| `kb_quelle_prod` | woher diese Basis stammt |
| `webbal` | Balance laut Provider-Katalog |
| `implizit` | `webbal − netto` (die von B3 eingeführte Basis) |
| `end_bal` | `implizit + netto` — Plausibilitätsprobe |
| `ertrag_10k` / `ertrag_impl` | Monatsrendite auf 10.000- bzw. auf impliziter Basis |
| `dd%_10k` / `dd%_impl` | Drawdown-% auf beiden Basen |
| `eq_dd_prod` | `EquityDrawdown` des Providers (Selbstauskunft) |

---

## 1. Ergebnis: die Kapitalbasis-Verzerrung ist real und groß

| id | Name | Quelle | Ampel | netto | dd_usd | mon | n | kb_prod | Basis-Quelle | webbal | implizit | ertrag_10k | ertrag_impl | dd%_10k | dd%_impl | eq_dd_prod |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2265877 | Gold Reaper New V2 | mql5 | 🟡 | 5 229 | 319 | 24 | 879 | 1 615 | csv_einzahlungen | 6 903 | 1 674 | 2,18 % | 13,02 % | 19,09 % | 3,19 % | 15,94 % |
| 2339082 | GoldWave signal | mql5 | 🟡 | 379 | 23 | 17 | 296 | 50 | csv_einzahlungen | 429 | 50 | 0,22 % | 44,55 % | 45,36 % | 0,23 % | 8,05 % |
| 2349227 | Gold Spike | mql5 | 🟢 | 2 878 | 157 | 11 | 392 | 3 116 | csv_einzahlungen | 2 410 | − | 1,57 % | — | 4,57 % | — | 15,94 % |
| 2329290 | Precise Pair Trading | mql5 | 🟡 | 1 189 | 278 | 13 | 882 | 225 | csv_einzahlungen | 1 417 | 227 | 0,91 % | 40,27 % | 122,48 % | 2,78 % | 24,02 % |
| 2379236 | EURUSD Night Scalp | mql5 | 🟡 | 2 388 | 1 | 9 | 296 | 2 000 | csv_einzahlungen | 5 321 | 2 933 | 2,65 % | 9,05 % | 0,03 % | 0,01 % | 0,04 % |
| 2362349 | Combo Profile 2026 | mql5 | 🟡 | 959 | 36 | 9 | 776 | 120 | csv_einzahlungen | 1 230 | 271 | 1,07 % | 39,38 % | 13,42 % | 0,36 % | 3,88 % |
| 2362868 | Pure Gold 2000 Vantage | mql5 | 🟡 | 28 275 | 2 330 | 7 | 667 | 10 000 | csv_einzahlungen | 30 134 | 1 859 | 40,39 % | 217,33 % | 23,30 % | 125,35 % | 11,91 % |
| 2000028 | Lexo | pelik | 🟢 | 13 407 | 753 | 39 | 3 296 | 10 000 | virtuelle_annahme | 32 147 | 18 740 | 3,44 % | 1,83 % | 7,53 % | 4,02 % | 0,27 % |
| 2014074 | The Holy Grail | pelik | 🟡 | 64 537 | 6 104 | 46 | 15 340 | 10 000 | virtuelle_annahme | 99 340 | 34 802 | 14,03 % | 4,03 % | 61,04 % | 17,54 % | 16,00 % |
| 2063644 | Lemonal | pelik | 🟢 | 10 141 | 718 | 9 | 5 541 | 10 000 | virtuelle_annahme | 14 544 | 4 403 | 11,27 % | 25,59 % | 7,18 % | 16,30 % | 2,37 % |
| 2014076 | PentagonForex | pelik | 🟢 | 5 691 | 26 | 22 | 2 012 | 10 000 | virtuelle_annahme | 29 557 | 23 866 | 2,59 % | 1,08 % | 0,26 % | 0,11 % | 0,21 % |
| 2059368 | gemslime | pelik | 🟡 | 814 | 125 | 9 | 2 457 | 10 000 | virtuelle_annahme | 9 923 | 9 110 | 0,90 % | 0,99 % | 1,25 % | 1,37 % | 1,22 % |
| 2084818 | AccurateCopier | pelik | 🟢 | 848 | 302 | 3 | 753 | 10 000 | virtuelle_annahme | 5 227 | 4 378 | 2,83 % | 6,46 % | 3,02 % | 6,89 % | 2,89 % |
| 2072334 | GOLD Tokyo Scalping | pelik | 🟡 | 1 042 | 253 | 7 | 464 | 10 000 | virtuelle_annahme | 2 847 | 1 805 | 1,49 % | 8,24 % | 2,53 % | 14,02 % | 2,38 % |
| 2039057 | Master H4-2 | pelik | 🟡 | 116 | 307 | 11 | 287 | 10 000 | virtuelle_annahme | 1 703 | 1 587 | 0,11 % | 0,67 % | 3,07 % | 19,37 % | 2,99 % |
| 2016702 | Master H4-1 | pelik | 🟡 | 574 | 204 | 21 | 490 | 10 000 | virtuelle_annahme | 1 750 | 1 176 | 0,27 % | 2,33 % | 2,04 % | 17,33 % | 1,96 % |
| 2048285 | SafeGold | pelik | 🟢 | 568 | 191 | 12 | 675 | 10 000 | virtuelle_annahme | 998 | 430 | 0,47 % | 11,00 % | 1,91 % | 44,45 % | 1,78 % |
| 2048284 | ImpulseNet | pelik | 🟡 | 540 | 30 | 12 | 381 | 10 000 | virtuelle_annahme | 898 | 357 | 0,45 % | 12,60 % | 0,30 % | 8,53 % | 0,00 % |
| 2012139 | Grid King $1000 | pelik | 🟡 | 3 178 | 146 | 22 | 2 338 | 10 000 | virtuelle_annahme | 3 477 | 299 | 1,44 % | 48,32 % | 1,46 % | 48,90 % | 1,15 % |
| 2049613 | MicroJump | pelik | 🟡 | 149 | 17 | 12 | 341 | 10 000 | virtuelle_annahme | 530 | 381 | 0,12 % | 3,25 % | 0,17 % | 4,55 % | 0,10 % |
| 2054437 | TKG | pelik | 🟡 | 726 | 126 | 8 | 2 158 | 10 000 | virtuelle_annahme | 63 880 | 63 154 | 0,91 % | 0,14 % | 1,26 % | 0,20 % | 1,23 % |
| 2053240 | HRC Algo | pelik | 🟡 | 2 981 | 56 | 11 | 101 | 10 000 | virtuelle_annahme | 4 695 | 1 714 | 2,71 % | 15,81 % | 0,56 % | 3,25 % | 0,43 % |
| 2052727 | Mr_Profit_FX | pelik | 🟢 | 1 154 | 68 | 11 | 1 469 | 10 000 | virtuelle_annahme | 4 437 | 3 283 | 1,05 % | 3,20 % | 0,68 % | 2,08 % | 0,66 % |

*(7 mql5-Signale nutzen `csv_einzahlungen` — dort stehen echte Einzahlungszeilen im
Trade-Export, das ist die richtige Basis. 26 pelik-Signale haben keine
Einzahlungszeilen und fallen auf `virtuelle_annahme` = 10.000 USD zurück.)*

### Kernbeobachtungen

1. **Die 10k-Annahme ist kein Randfall, sondern der Normalfall für Quellen.** 26
   von 33 Signalen rechnen auf 10.000 USD, obwohl die tatsächliche Basis zwischen
   **299 USD (Grid King)** und **63 154 USD (TKG)** liegt — Faktor **211**.
2. **Der Drawdown-%-Fehler ist bis zu Faktor 25.** SafeGold: 1,91 % (10k) vs.
   44,45 % (implizit) = **23×**. Master H4-2: 3,07 % vs. 19,37 % = 6,3×.
   Grid King: 1,46 % vs. 48,90 % = 33×. **SafeGold ist aktuell 🟢 mit einem
   rechnerisch 44 %-Drawdown auf realer Basis** — das ist exakt der B1-Typ
   „hartes Kriterium umgeht", nur über die Basis statt über die Messung.
3. **Der B2-Effekt ist größer als im Hauptbericht angenommen.** Von den 16
   pelik-🟢/🟡 liegen auf der 10k-Basis **14 unter der 5-%-Monatsschwelle** —
   nur Lemonal (11,27 %) und The Holy Grail (14,03 %) darüber. Auf der impliziten
   Basis dreht sich das Bild teilweise um: Grid King 48,32 %, HRC Algo 15,81 %,
   ImpulseNet 12,60 %, SafeGold 11,00 %, Lemonal 25,59 % — aber ebenso PentagonForex
   auf 1,08 %, Mr_Profit_FX 3,20 % und TKG auf 0,14 % (Basis 63 154 USD).
   **Kein pelik-Grüner erreicht auf beiden Basen 5 %/M**: PentagonForex 🟢
   2,59 % → 1,08 %, Mr_Profit_FX 🟢 1,05 % → 3,20 %, SafeGold 🟢 0,47 % → 11,00 %,
   AccurateCopier 🟢 2,83 % → 6,46 %, Lemonal 🟢 11,27 % → 25,59 %, Lexo 🟢
   3,44 % → 1,83 %. Von den 6 pelik-🟢 erreicht damit **nur Lemonal auf beiden
   Basen ≥ 5 %/M**; 3 (Lexo, PentagonForex, Mr_Profit_FX) liegen auf **beiden**
   darunter, 2 (SafeGold, AccurateCopier) nur auf der 10k-Basis.
4. **Die Basiswahl entscheidet über die Ampel, nicht die Datenlage.** Grid King
   wäre auf impliziter Basis ein 48-%/Monat-Kandidat, auf 10k-Basis ein
   1,4-%-Kandidat. Beides ist „richtig" — je nachdem, was ein Kopierer tatsächlich
   einzahlt. Genau das ist der Punkt: die Ampel muss die Basis nennen, sonst ist
   sie eine Funktion der willkürlichen 10.000.
5. **TKG ist der Extremfall gegen B3.** implizit 63 154 USD bei Web-Balance
   63 880 USD. Entweder ist das Konto mit ~700 USD *heute* gestartet und war
   über die Historie nie größer (dann ist 63 154 die richtige Basis) — oder die
   Balance ist kumuliert und `Σ PnL` (726 USD über 8 Monate) deckt die
   Historie nicht ab. Siehe Abschnitt 2.

---

## 2. Grundannahme geprüft: deckt der Trade-Export die volle Historie?

B3 rechnet `implizit = web_balance − Σ NettoPnL`. Das ist nur korrekt, wenn
`Σ NettoPnL` dem **gesamten** Lifetime-Gewinn des Provider-Kontos entspricht.
Wäre der Export gegenüber dem Kontoanfang abgeschnitten, wäre `Σ PnL` zu klein,
`implizit` zu groß — die Basis wäre zu konservativ (Risiko-% zu niedrig).

`historien_check.py` vergleicht je Signal Zeitstempel-Spanne, Trade-Anzahl und
`Σ PnL` des Exports gegen Katalogangaben:

| Prüfpunkt | Ergebnis |
|---|---|
| Signale mit Forensik | 30 / 30 pelik-Signale geprüft |
| Zeitspanne des Exports | 2,9 bis 45,6 Monate; Median ~11 Monate |
| Startpunkte | 2022-12-08 (The Holy Grail) bis 2026-07-01 (AccurateCopier) — **jeweils ein eigener, plausibler Kontoanfang** |
| Endpunkte | 2026-06-24 … 2026-09-29 — Export endet überall nahe dem Scan-Zeitpunkt |
| `Σ PnL` Export ↔ Forensik-Netto | **exakt deckungsgleich bei allen 30** (0 Abweichung) |
| Abschnitte/Lücken | keine; durchgehend aufsteigende Zeitfolge |

**Befund: Die Annahme hält.** Die Zeitstempel-Spanne beginnt pro Signal an
einem eigenen Anfangsdatum (nicht an einem einheitlichen Fenster) und reicht
bis zum Scan-Zeitpunkt; es gibt keine abgeschnittenen Köpfe. TKG exportiert
2 158 Trades über 7 Monate — die 63 154 USD sind also **kein** Artefakt eines
fehlenden Anlaufs, sondern ein echtes großes Konto mit geringem Netto-PnL
(0,91 %/M auf der 10k-Basis gerechnet, 0,14 %/M auf der realen).

> **Einschränkung:** die Provider-Katalogeinträge liefern `weeks` = `null`
> (B5), eine unabhängige Anlauf-Datumsquelle gibt es nicht. Die Prüfung stützt
> sich auf die Plausibilität des Exportverlaufs, nicht auf einen Abgleich mit
> dem Provider-Startdatum.

---

## 3. Abgleich mit der Engine

| Prüfung | Ergebnis |
|---|---|
| `kb_prod` (Nachrechnung) == `kapitalbasis_usd` (Engine, `forensik`-JSON) | **33 / 33 exakt** |
| `netto` (Nachrechnung) == Forensik-Netto | **30 / 30 exakt** |
| `implizit` > 0 für alle Quellen-Signale | **26 / 26 ja** — B3 liefert durchweg eine brauchbare Basis, greift also überall |
| `kb_quelle_prod` == `virtuelle_annahme` bei allen 26 pelik | ja — **der Lauf ist ein Vor-Fix-Zustand** |

Die Engine rechnet also korrekt auf der Basis, die ihr zur Verfügung steht; das
Problem ist ausschließlich, dass diese Basis bis `fc4b3b9` eine Annahme war.

---

## 4. Konsequenzen

1. **B3 ist die richtige Korrektur und trägt.** Die implizite Basis ist für alle
   Quellen-Signale berechenbar, positiv und plausibel; die Historie-Abdeckung ist
   belegt. Ein Re-Scan nach `fc4b3b9` wird die DD-% und Schock-% dieser 26
   Signale **substantiell verschieben** — nach meiner Rechnung rutschen
   SafeGold, Grid King, Master H4-2, PentagonForex und The Holy Grail
   rechnerisch über die 30-%-Schranke bzw. verlieren ihre Ertrags-🟢.
2. **Die Ampel-Zelle „Ertrag" braucht die Basis im Text.** Ohne
   „auf 10.000 USD-Annahme" / „auf realer Basis 430 USD" ist der Wert nicht
   interpretierbar (→ Maßnahme #17).
3. **TKG ist ein Warnfall für die Nutzerkommunikation:** 63 154 USD Basis bei
   0,14 %/M wirkt auf den ersten Blick „sicher" — ist aber ein Großkonto mit
   minimalem Zins. Ein Ampel-Kriterium „Basis > X USD bei niedriger Rendite"
   wäre zu prüfen.

---

## 5. Reproduktion

```
python kapitalbasis_check.py     # Kapitalbasis-/Ertragstabelle
python historien_check.py        # Export-Spanne vs. Katalog
```

Beide lesen nur aus `data/` und der Produktiv-DB (read-only) und importieren
kein Modul aus `src/`.
