# MT5-Exporttyp „Deal Interestrate“

Die vollständige Offlineprüfung des echten Quellenjobs
`u-35579920-eb3d-4db4-83ef-ae6a24b934c9` fand in MT5-Signal 2236750
38 Zeilen dieses Typs. Ausschließlich `Time`, `Type` und `Profit` sind
belegt; Symbol, Volumen, Positionszeiten und Preise fehlen. Der damalige
Scannerparser wies dadurch die gesamte Datei ab. Das ist eine belegte
Parsergrenze, kein fehlgeschlagener Download. Struktur und Originaldatei
liegen ausschließlich im privaten Laufbeleg beziehungsweise dessen Backup.

Die offizielle [MQL5-Referenz zu Deal Properties](https://www.mql5.com/en/docs/constants/tradingconstants/dealproperties)
führt `DEAL_TYPE_INTEREST` als Zinsoperation getrennt von
`DEAL_TYPE_BALANCE`, `DEAL_TYPE_CREDIT` und Handelsabschlüssen auf.
Der exakte CSV-Text „Deal Interestrate“ steht dort nicht. Die Zuordnung
dieses Exporttexts zur Zinsoperation ist eine begründete Inferenz aus
Bezeichnung und der beobachteten reinen Geldbuchungsstruktur; die CSV
enthält keine numerische Enum-ID als zusätzlichen Beleg.

Die vorhandene `AccountCostRow`-Verarbeitung bewahrt das Vorzeichen und
berücksichtigt Geldbuchungen im realisierten Ergebnis, Closing- und
H1-Equity-Verlauf sowie in der Monatsrendite. Sie neutralisiert sie nicht
als externe Einzahlung und erzeugt keine künstliche Position. Die
Verbraucher-Tests decken bereits positive Korrekturen ab. Diese Struktur
eignet sich auch für positive oder negative Zinsbuchungen. Der Typname
`costs` rechtfertigt keine Umkehr oder Beschränkung des Vorzeichens.

Empfehlung aus der lesenden Prüfung: ausschließlich den exakt belegten
MT5-Typ mit unverändert strenger Spalten-/Zahlenprüfung zulassen;
sonstige unbekannte „Deal“-Typen weiterhin ablehnen. Der Hauptagent
besitzt Parseränderung und gesonderte Nachabnahme. Der ursprüngliche
Quellenbeleg bewahrt die damalige Parsergrenze unverändert.
