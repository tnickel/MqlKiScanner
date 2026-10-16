# Read-only Gegenprüfung der Scanner-Anzeigekorrekturen

Geprüft: Root-Änderungen in `station_dialoge.py`, `help_content.py`, `ampel_matrix.py` sowie die geänderten Stationstests, gegenüber Scanner-HEAD `cef1e5af53e5737eb3dfdc2e093c8b7b979a83b5`. Keine Produktdateien geändert und keine Tests erneut gestartet; kombinierte Ausführung bei Root.

## Bestätigt korrekt

- Station3 verwendet sowohl im Auswahlrecord-Zweig (`station_dialoge.py:525`) als auch beim ergänzten DB-/Sitzungsergebnis (`:547`) `true_retdd_jahr` und `retdd_jahr_vorbehalt`. `60% CAGR / 10% DD = 6` ist der richtige Jahreswert; `4% Monatsrendite / 10% DD = 0,4` wäre eine andere Größe. Die neuen parametrisierten AppTests decken beide tatsächlichen Tabellenzweige ab.
- Der Vorbehalt geht nicht verloren: `true_retdd_jahr` liefert bei fehlendem belastbarem Jahreswert den Jahres-Vorbehalt. Der Tabellenstil prüft die ebenfalls umgestellte Vorbehaltsspalte und färbt die Hauptanzeige weiterhin orange. `refresh_efficiency()` setzt den Vorbehalt bei zu kurzer/veralteter Historie zurück. Die bestehende Vorbehaltsprobe wurde folgerichtig auf `18,2 / 13,83` umgestellt.
- Die Station3-Caption nimmt die aktive Schwelle aus `config.min_calmar_jahr(settings)` und formatiert sie mit Dezimalkomma. Der AppTest mit Schwelle4,25 ist dafür eine brauchbare Regression.
- Keine Auswirkung auf Ampel/Score/DB erkennbar: geändert wurden gelesene Anzeigeproperties und Texte. Das bereits vorhandene `refresh_efficiency()` ist keine neu eingeführte Bewertungsausführung. Weder `ampel_for`, Persistenz noch numerische Matrixzellen wurden geändert.
- Die neuen Monitor-Texte in Hilfe, Station3 und DD-Tooltip sind korrekt: eigene freigegebene Kursrekonstruktion erfasst Floating der exportierten Positionen; Monitor-DD ist Closing-DD und kein Ersatz für historischen Floating-DD oder den Calmar-Nenner.
- Der neue Gelb-/Score-Hinweis beseitigt ein altes falsches Gate. Score bleibt Zusatzinformation, Ertrag/Jahres-Calmar und harte Regeln entscheiden die Ampel.
- Der neue Exposure-Hilfetext passt zur Engine: `exposure.py:447–459` nimmt Lots und Dollar-Schock aus `risk_snap`, während der Positionsanzahl-Peak separat erhalten bleibt. Instrumente werden nicht einfach symbolübergreifend als Hedge netto verrechnet; bei unvollständiger Umrechnung bleiben vergleichbare Dollar-/Lotwerte unbekannt.

## Verwandte aktuelle Restpfade an Root gemeldet

1. **Station5 zeigt noch den Monatswert unter derselben TrueRetDD-Bezeichnung.** `station_dialoge.py:666–667` liest im Portfolio-Basistableau weiterhin `true_retdd_monat` / `retdd_monat_vorbehalt`. Damit zeigt ein identischer Kandidat in Station3 nun6, in Station5 weiterhin0,4. Vorbestehender Restfehler, keine Regression der neuen Station3-Zweige. Entweder ebenfalls Jahresfelder verwenden oder ausdrücklich Monats-RetDD benennen. Root hat die exakten Stellen erhalten; keine Edits durch Peer.

2. **Schock-Tooltip ist noch pauschal auf50 USD formuliert.** `ampel_matrix.py:112–116` nennt weiterhin „Peak-Netto-Exposure im50-USD-Schock“ und „Expositionspeak“. Die jetzt korrekte Hilfe und Engine unterscheiden instrumentabhängige Schocks und das maximale berechnete Dollar-Schockereignis vom Anzahlmaximum. Der Tooltip sollte dieselbe Bedeutung verwenden;50 USD gilt als Gold-Standardprobe, nicht als universelle Schockdefinition für alle Instrumente. Reiner Textrest, kein nachgewiesener Rechenfehler.

## Prüfsumme dieses Lesestands

```text
station_dialoge.py           08bf0d1fb769075f188b5866acccc4473a72e9e7dc4ce6b367d5d6014d0b0ce8
help_content.py              d77735e3a054f87a50cfdb7c1662d760e7c0ae1af29bc90ab650acc1a5b171f1
ampel_matrix.py              bb8ed7300acc2e2a2346daaab5cb9cc3af2b74967eaa9a295c608a54e2943597
test_scan_station_details.py e5d81651c7cd52e04536914da95ce09aa58856450b43d8f972a093154583f81c
```

Dieser Nachweis bezieht sich auf den gelesenen Zwischenstand. Änderungen von Root an den zwei gemeldeten Reststellen benötigen dessen abschließenden Snapshot-/Testnachweis; hier wird kein ungeprüfter späterer Stand freigegeben.

## Finale Gegenprüfung nach den beiden Restkorrekturen

Beide gemeldeten Reststellen sind im erneut gelesenen finalen Stand korrigiert:

- Station5 (`station_dialoge.py:666–667`) verwendet nun `true_retdd_jahr` und `retdd_jahr_vorbehalt`. Der vorhandene orange Stil prüft den jährlichen Vorbehaltsmarker. Der neue Portfolio-AppTest hat getrennte Fälle für belastbaren Jahres-Calmar und den Jahres-Vorbehalt; beide erwarten korrekt6 statt Monatswert0,4. Das gelesene Vorherlog `ui_portfolio_before.log` belegt exakt diese zwei vorher fehlgeschlagenen Fälle. Keine Neuberechnung der Ampel oder andere Änderung an Bewertungsregeln durch diesen Tabellenwechsel.
- Der Schock-Tooltip (`ampel_matrix.py:112–117`) benennt jetzt das maximale berechnete Dollar-Schockereignis mit instrumentabhängigen Kontrakten/Schockbewegungen und dem Kontobezug am gleichen Schockzeitpunkt. Die pauschale50-USD-Formulierung ist entfernt. Das passt zur bereits geprüften `risk_snap`-Auswahl in der Engine.

**Keine weiteren konkreten Regressionsbefunde in den beauftragten Pfaden.** Keine Produkt-/Snapshotedits oder Teststarts durch diesen Peer. Die vollständige Suite von Root lief bei diesem Abgleich noch; deshalb wird hier kein Endergebnis des laufenden Tests behauptet.

Alle vier Dateihashes wurden direkt mit den Dateien im eingefrorenen `Scanner_final2` und dessen `Scanner_final2.manifest.json` verglichen: **Live = Snapshot = Manifest**.

```text
station_dialoge.py           24600e8835e80c7ddfcf3a72b0d4e6bad6e83fc4d0e6bb41bc41a89b94aefa79
help_content.py              d77735e3a054f87a50cfdb7c1662d760e7c0ae1af29bc90ab650acc1a5b171f1
ampel_matrix.py              9a994f03c4165570102152ca95080577bfe1098feb7f77875a5aae88d6bebde3
test_scan_station_details.py ca4ad3a670993784d43485e4076055a424562085af755e333ddadafb9b8aca28
```

Finaler Snapshotpfad: `D:\AntiGravitySoftware\GitWorkspace\SIGNALDOWNLOADER\waste\deepseek_review_pruefung_2026-10-16\Scanner_final2`. Die frühere Prüfsummenliste bleibt als datierter Zwischenstand erhalten und ist durch diese finale Liste ersetzt.
