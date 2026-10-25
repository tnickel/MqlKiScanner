# Weitere Kontrakte und historische USD-Umrechnung

`Nikkei225` und `Soybean-C` wurden am 18.10.2026 direkt mit
`MetaTrader5.symbol_info` am portablen Vantage-Terminal auf
`VantageMarkets-Live 10` gelesen. Die Namen wurden nur in der Gross-/
Kleinschreibung wiederhergestellt; andere Indizes, Futures oder Rohstoffe
wurden nicht als Ersatz verwendet. Das gemeinsame Scan-/Studienlock war
vor dem ersten Prozess-/Terminalzugriff belegt. `account_info` wurde nur
fuer den Servernamen gelesen. Das zuvor nicht laufende Terminal war nach
Cleanup beendet. `contracts_terminal_spec.json` enthaelt den Originalbeleg,
`scripts/reference/remaining_contract_beleg.py` den reproduzierbaren Helper.

| Exaktes Instrument | Kontraktgroesse | Gewinnwaehrung | Berechnungsmodus |
|---|---:|---|---:|
| Nikkei225 | 1 | JPY | 2 (CFD) |
| Soybean-C | 500 | USD | 2 (CFD) |

Die Registry verwendet diese nativen Faktoren ausschliesslich im
dokumentierten Vantage-Familienprofil (`cross_broker=false`). Der aktuelle
Referenzserver beweist weiterhin keinen historischen Provider-Originalserver;
dieser bleibt unbekannt. Fremde Broker erhalten keine Freigabe. Die
Broker-Tickwerte wurden nicht als USD-Faktoren interpretiert: sie koennen in
der Waehrung des verbundenen Kontos vorliegen. Gewinnwaehrung, nativer
Kontraktfaktor und historischer Umrechnungskurs bleiben getrennt.

Das Nikkei-Schockszenario von 3.000 Punkten folgt dem vorhandenen
Nikkei-Indexszenario. Das Soybean-Szenario von 10 % verwendet den
volumengewichteten Einstand gerade offener Positionen desselben Signals.
Beide sind editierbare Szenarien, keine Terminalmetadaten. Exakte
Vantage-Kursnamen stehen in `symbols.SYMBOL_ALIASE_DEFAULT`; es wurde kein
Kursproxy ergaenzt.

## CNH und ETH: bestaetigte Ursache und Korrektur

Die vorherigen FT-Gesamtsperren in `vant/178177` und `vant/504191` kamen
nicht von einer zu alten EUR-/GBP-Tabelle. Es fehlten `USDCNH (CNH)` und
zusaetzlich `BTCETH (ETH)`. Die EZB-Historie fuehrt weder CNH noch ETH.
CNH wird nicht mit CNY gleichgesetzt; ein neuer Download kann diese beiden
Waehrungen nicht ergaenzen.

Der Exposure-Test kann jetzt mit dem vorhandenen Kursanbieter einen
zusaetzlichen H1-Kanal verwenden:

- CNH-Betraege aus USDCNH: Kehrwert des eigenen USDCNH-Referenzkurses.
- ETH/BCH-Betraege: direkter ETHUSD-/BCHUSD-Referenzkurs aus demselben
  nachgewiesenen Terminal-/Brokerserverfeed wie die Handelsbars.
- Die Ereigniszeit muss durch den vorhandenen Preis-/GMT-Abgleich belegt
  sein. Bei einem ruhigen Instrument duerfen andere Preisereignisse desselben
  Exports im selben Zeitfenster und Referenzfeed den gemeinsamen Versatz
  belegen. Eigene Open-/Close-Preise werden danach weiterhin geprueft;
  Toleranzen und Eindeutigkeitsanforderungen sind unveraendert.
- Verwendet wird nur der letzte bereits abgeschlossene H1-Close vor oder
  am Ereignis, weniger als eine Stunde alt. Fehlende Vorstundenbars,
  mehrdeutige Zeitbasis, Serverwechsel und ungueltige Kurse bleiben unbekannt.
  Eine spaetere Bar oder Wochenendfortschreibung ersetzt keinen Beleg.

Der neue `forensics.exposure_fx.ExposureUsdUmrechnung` protokolliert
Umrechnungssymbol, Referenz-Bar-Ende, Feed und Preis-/Zeitbasis. Solche Kurse
werden nicht als EZB-Kurse ausgegeben. Das bestehende Verhalten ohne
Kursanbieter bleibt konservativ gesperrt. Die Engine prueft unbekannte
Kontrakte weiterhin vor dem ersten Kurszugriff. Nach der Equity-Rekonstruktion
wiederholt sie nur einen verbleibenden Nicht-EZB-Exposure-Fall mit dem
bereits gefuellten H1-Cache; historische Marktluecken werden so nicht fuer
denselben Lauf doppelt abgefragt.

Diese Modellergänzung erfordert Forensikversion **21**. Kapitalbasis,
H1-/Floating-Anforderung fuer Calmar, DD-Schranke und SL-Neutralitaet wurden
nicht geaendert. Ein Exposure-Szenario ersetzt keine aktuelle Equity-Studie.

## Durchgefuehrte Aktualisierung und Nachweise

Der EZB-Cache wurde einmal explizit ueber den vorhandenen produktiven
Downloadpfad aktualisiert. Letzter USD-Kurstag ist jetzt **16.10.2026**
(vorher 15.10.2026); Vorher-/Nachher-SHA und Waehrungsumfang stehen in
`contracts_ecb_update.json`. Private Kurs- und Trade-Caches bleiben ausserhalb
der Reviewanhaenge.

`contracts_live_recalculation.py` liest Schema-2-Besitzer und SHA-gepruefte
vorhandene FT-Snapshots, haelt das gemeinsame Lauf-Lock und benutzt den
regulaeren portablen Kursanbieter mit abschliessendem Cleanup. Es aktualisiert
H1-Originalbars im produktiven Kurscache, schreibt aber keine Signalurteile,
Studien, Kapitalannahmen oder Trade-Exporte. Die Vollstaendigkeit/UTC-Qualitaet
der alten Quellenhistorien wird durch diese Nachrechnung nicht zertifiziert.
Die Quellenerneuerung und anschliessenden produktiven Neubewertungen werden
im Hauptbericht dieses Reviewordners getrennt nachgewiesen.

`contracts_live_recalculation_initial.json` ist ausschliesslich eine erhaltene
Diagnose: instrumentinterne Zeitableitung ohne den spaeter ergaenzten
gemeinsamen Export-/Feed-Beleg; waehrend dieses ersten Laufs wurde ausserdem
der EZB-Cache erneuert. Die abschliessende Nachrechnung steht in
`contracts_live_recalculation.json` und verwendet den aktualisierten EZB-Cache.

Abschluss des Live-Nachlaufs: vier von fuenf vorhandenen FT-Snapshots sind
jetzt kontrakt- und USD-umrechnungsvollstaendig: 178177, 1231244, 692325,
762452. In 504191 ist CNH ebenfalls geloest; es fehlt ausschliesslich der
eigene Preisbeleg fuer einzelne BTCETH-Trades. Der Cache-SHA blieb waehrend
des abschliessenden Laufs unveraendert; Terminal-Cleanup wurde bestaetigt.

Die anschliessende rein lesende Diagnose `contracts_btceth_gap_diagnosis.*`
grenzt die verbleibende Sperre ein: 3 von 37 BTCETH-Trades haben zusammen
4 Open-/Close-Preise ausserhalb der eigenen Referenzbar plus unveraenderter
0,1-%-Toleranz; maximaler Abstand ausserhalb der Bar 0,8622 %. Hier fehlen
keine eigenen Ereignisbars, und die wochenweise Zeitbasis mit +1/+2 Stunden
ist strukturell belegt. Das beweist keine falschen Providerdaten: Spread,
Referenzfeed und einzelne Ausfuehrungen bleiben moegliche Ursachen. Ohne
passenden Preisbeleg wird dieser alte Gesamtsnapshot nicht freigegeben.
Die aktuelle Quellenhistorie muss davon getrennt erneut geprueft werden.

Gezielte Regression: **342 bestanden**, Exit 0. Befehl, vollständiges Log und
JUnit stehen in `contracts_tests_command.json`, `contracts_tests.log`,
`contracts_tests_exit.txt` und `contracts_tests.xml`. Abgedeckt sind die beiden
exakten Kontrakte/Brokergrenzen, Lock/Cleanup, nativer Faktor/Quote,
historische EZB-Kurse, eigene CNH-Inversion, Crypto-Direktkurs, gemeinsamer
Zeitbeleg, Serverwechsel, fehlende/ungueltige Bars, kein Zukunftsclose,
CNH ungleich CNY, vorsichtiger Betrieb ohne Anbieter und die Engine-Reihenfolge.
