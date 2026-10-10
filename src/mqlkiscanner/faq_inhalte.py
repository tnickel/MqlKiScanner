# -*- coding: utf-8 -*-
"""FAQ-Inhalte der Web-App — die Fragen des Nutzers, praxisnah beantwortet.

ERWEITERN (Nutzer-Wunsch 08.10.2026): Neue Frage = unten in der passenden
Kategorie einen weiteren Eintrag `("Frage?", "Antwort als **Markdown**")`
anhängen — die Seite rendert automatisch. Neue Kategorie = neuen Dict-Eintrag
in `FAQ_KATEGORIEN` ergänzen.

Die Antworten beschreiben den IST-Zustand des Tools (Stand 08.10.2026) und
bleiben bewusst zeitlos formuliert — konkrete Stichproben-Zahlen (z. B.
„249 Signale") nur, wenn sie ein Prinzip veranschaulichen.
"""

FAQ_KATEGORIEN: list[dict] = [
    {
        "titel": "Signale finden & laden",
        "icon": "🔍",
        "fragen": [
            (
                "Warum finde ich ein bestimmtes Signal nicht in „Alle Signale“?",
                "Zwei mögliche Gründe, beide behebbar:\n\n"
                "1. **Der Katalog ist nicht frisch.** Die Übersicht zeigt den Katalog "
                "der Monitor-Clients (VantageMonitor, RoboMonitor & Co.). Oben auf "
                "der Seite den Button **„Katalog von den Clients laden“** drücken — "
                "danach sollte das Signal da sein, wenn der Client es meldet. Fehlt "
                "es auch dort, meldet der Client es nicht (siehe Frage zu „die "
                "besten Signale“).\n"
                "2. **Der Workflow-Vorfilter hat es ausgespart.** Der SCAN filtert "
                "bewusst: Mindestalter **26 Wochen** und Mindestabonnenten. Ein "
                "junges Signal mit vielen Abonnenten (Beispiel: DINO Scalping, 17 "
                "Wochen) bleibt so lange außen, bis es alt genug ist. Der Grund "
                "steht nachvollziehbar in `data/auswahl_begruendung.json` "
                "(Status „DRAUSSEN“ mit Begründung).\n\n"
                "Das **Anschauen** (Statistik, Drawdown-Check, Equity-Studie) geht "
                "auch ohne Scan — siehe nächste Fragen."),
            (
                "Wann wird die Signalliste aktualisiert? Wo ist der Download-Button?",
                "Direkt auf der Seite „Alle Signale“ oben: **„Katalog von den "
                "Clients laden“** — der zieht die gemeldeten Signale live per REST "
                "von den laufenden Monitor-Clients (dauert ~1 Sekunde). Beim ersten "
                "Start lädt die Seite den Katalog einmal automatisch.\n\n"
                "Unabhängig davon holt jeder **Scan-Lauf** den Katalog ebenfalls "
                "frisch (Modus „beides“): Signale laden → Vorfilter → Forensik. "
                "Mit Automatik passiert das zeitgesteuert, sonst manuell."),
            (
                "Welche Signale laden wir überhaupt — sind das die besten?",
                "Definiert: **die Besten = viele Abonnenten. Signale ohne Abonnenten "
                "laden wir nicht.** Die Clients laden entsprechend:\n\n"
                "- **RoboForex (CopyFX):** Rating serverseitig nach "
                "Abonnentenzahl absteigend — Top-N nach Abonnenten.\n"
                "- **Pelican:** die VOLLSTÄNDIGE Strategieliste (~2.200) — nichts "
                "kann fehlen.\n"
                "- **MQL5:** die Standard-Listen (populärste zuerst) — die "
                "abonnentenstärksten sind immer in den ersten Seiten.\n"
                "- **Vantage:** Sortierung nach **Kopierern** primär, danach "
                "Rendite als Auffüllung. (Bis 08.10.2026 wurde nur nach 1-Monats-"
                "Rendite sortiert — damit fehlten abonnentenstarke Signale mit "
                "ruhigem Monat, z. B. das kopiererstärkste Signal insgesamt.)\n\n"
                "Der Scanner filtert dann die gemeldeten Signale auf "
                "Abonnenten ≥ 1 und macht die eigentliche Qualitätsprüfung "
                "mit Forensik und Ampel — Abonnentenzahl ist Vorauswahl, kein "
                "Qualitätsurteil (sie korreliert mit Marketing/Alter, nicht mit "
                "Risikofreiheit)."),
            (
                "Was bedeutet „Herkunft: Katalog“ vs. „Workflow“ in der Tabelle?",
                "**Workflow** = das Signal ist bereits gescannt: es hat Ampel, "
                "Forensik und ggf. KI-Berichte.\n\n"
                "**Katalog** = das Signal ist nur gemeldet (im Client-Katalog), aber "
                "noch nicht Teil eines Scan-Laufs — Ampel/Forensik entstehen erst "
                "beim Scan. Katalog-Zeilen ohne lokalen Trade-Cache laden ihre "
                "Trades per Zeilenauswahl **on demand** vom Client (Button im "
                "Detail). Danach rechnen alle Kennzahlen und die Equity-Studie — "
                "ein echter Drawdown-Check ist also auch für nie gescannte Signale "
                "möglich."),
            (
                "Wir haben doch alles zum Server hochgeladen — warum fehlen Signale?",
                "Das sind zwei verschiedene Richtungen: Der **Server-Upload** "
                "(monitor.tnickel-ki.de) überträgt die Scanner-ERGEBNISSE nach "
                "außen (Tabelle + PDFs für den MqlTradeMonitor). Die "
                "Signal-KATALOGe kommen umgekehrt **von den lokalen Monitor-"
                "Clients** in den Scanner (REST, Ports 8089–8093). Was auf dem "
                "Server landet, beeinflusst also nicht, welche Signale hier "
                "erscheinen — dafür ist der Katalog-Button bzw. der Scan zuständig."),
        ],
    },
    {
        "titel": "Kennzahlen & Drawdown",
        "icon": "📈",
        "fragen": [
            (
                "Warum sind bei vielen (Vantage-)Signalen die Prozentwerte leer?",
                "Für Prozentwerte (Gewinn %/Monat, RetDD) braucht das Tool eine "
                "**belegbare Kapitalbasis**. Der Vantage-Export enthält keine "
                "Einzahlungs-/Balance-Zeilen und die Vantage-API liefert kein "
                "„Initial Deposit“ — deshalb bleiben Prozentwerte ehrlich LEER und "
                "nur die USD-Werte (Netto, Trading-DD USD) werden gerechnet. Wo der "
                "Client eine virtuelle Basis meldet (10.000-USD-Annahme, klar "
                "markiert), rechnet die Seite damit und zeigt „Basis: virtuell“. "
                "Eine erfundene Basis wird es nie geben — lieber keine Prozentzahl "
                "als eine falsche."),
            (
                "Welche Drawdown-Spalte ist die richtige — Plattform-DD, Trading-DD oder True-DD?",
                "Alle drei messen VERSCHIEDENES — und die Plattform-Werte sind "
                "untereinander nicht vergleichbar:\n\n"
                "- **Plattform-DD %** = Broker-/Client-Selbstauskunft. Vantage "
                "rechnet vermutlich Peak-zu-Tief vom Equity-Höchststand, MQL5 "
                "„By Equity“ dagegen offener Verlust ÷ aktuelle Balance — eine "
                "14 % von Vantage und eine 14 % von MQL5 sind NICHT dasselbe.\n"
                "- **Trading-DD %** = größter Rückgang der Kurve GESCHLOSSENER "
                "Trades (ohne offenes Floating) — fällt ohne Kapitalbasis verzerrt "
                "hoch aus.\n"
                "- **True-DD %** = der ECHTE Max-Drawdown: Equity inkl. schwebender "
                "Verluste, stundenfein aus H1-Kursen nachgemessen (Equity-Studie). "
                "Nur er zählt als Nenner für TrueRetDD und für die 30-%-Schranke.\n\n"
                "Das „≈“-Zeichen (orange) bedeutet: nur roh gemessen, "
                "Verlässlichkeitsprüfung nicht bestanden — orientierend, nie "
                "Grün-Beleg."),
            (
                "Berechnet Vantage den Drawdown als High-Watermark-Drawdown?",
                "Belegt ist der High-Watermark bei Vantage nur für die "
                "**Leistungsgebühren** (Performance Fee erst oberhalb des letzten "
                "Equity-Höchststands). Für die **Drawdown-Metrik selbst** "
                "(`maxDrawDown` in der API) publiziert Vantage keine Formel — das "
                "Help Center definiert nur Warn-/Stop-Schwellen. Peak-zu-Tief ist "
                "naheliegend, aber unbelegt.\n\n"
                "Empirisch weicht die Selbstauskunft stark von unserer eigenen "
                "Messung ab (Stichprobe 08.10.2026: gemeldet 14,4 % vs. ≈ 45 % in "
                "der eigenen Trade-Kurve; andere Signale umgekehrt) — Gründe sind "
                "Einzahlungen (heben den HWM), Floating-Marks und Zeitfenster. "
                "Deshalb gilt: Plattform-DD = Anzeige, eigener True-DD aus Kursen "
                "= Beleg."),
            (
                "Was ist TrueRetDD — und wann ist es „grün“?",
                "**TrueRetDD = echter Jahres-Calmar**: CAGR ÷ belastbar gemessenem "
                "Max-Drawdown der Equity INKL. schwebender Verluste (aus Kursen, "
                "nie aus geschlossenen Trades, nie Plattform-Angabe). Grün-Gate ab "
                "**3,0** (Entscheid 05.10.2026; Calmar 3,0 gilt branchenüblich als "
                "sehr gut). Der Wert erscheint nur, wenn die Kursmessung die "
                "Verlässlichkeitsprüfung bestanden hat — sonst steht der "
                "orange-markierte Vorbehaltswert „TrueRetDD ≈“ (roher Kurs-DD als "
                "Nenner), der nur orientiert und nie Grün liefert. Das „?“ an der "
                "KPI-Karte im Detail öffnet Formel, ausgerechnete Rechnung und "
                "Erklärung."),
            (
                "Was bedeutet „Ertrag je Close-DD ⚠“?",
                "Eine gekennzeichnete **VORBEWERTUNG** für Signale ohne eigene "
                "Kursmessung: geometrischer Ertrag ÷ Trading-DD (nur geschlossene "
                "Trades). Der Nenner kennt offene Verluste nicht — die Zahl fällt "
                "deshalb typischerweise zu schön aus. Sie ist kein TrueRetDD und "
                "sperrt Grün. Empfehlung steht daneben: Equity-DD-Studie öffnen "
                "(Button im Detail), dann wird aus der Vorbewertung eine echte "
                "Messung."),
        ],
    },
    {
        "titel": "Trade-Daten",
        "icon": "🧾",
        "fragen": [
            (
                "Fehlen bei den Vantage-Trades die Start- und Endzeiten?",
                "Nein — die stehen in **jeder Zeile**: Die Vantage-CSV nutzt das "
                "MQL5-Positions-Format mit doppelt belegten Headern („Time“, "
                "„Volume“, „Price“ je zweimal). **Spalte 1 = Eröffnungszeit, "
                "Spalte 7 = Close-Zeit.** Excel benennt doppelte Header nur um "
                "(„Time1“…) — die Daten sind da. Das Tool rechnet darauf sauber: "
                "die Tradeliste im Detail zeigt Eröffnet/Geschlossen/Dauer je "
                "Trade, und die Haltezeit-Statistik (Median, längster Trade, "
                "0-Sekunden-Anteil) basiert exakt auf diesen Zeitpaaren "
                "(Kontrollprobe: 1.181 Trades, 0 mit kaputter Zeitlogik)."),
            (
                "Sind die geladenen Trades vollständig?",
                "Meist ja, mit drei bekannten Grenzen:\n\n"
                "1. **2.000-Trade-Deckel** bei Vantage-Batch-Downloads: Liegt eine "
                "Datei EXAKT bei 2.000 Trades, sind das nur die NEUESTEN 2.000 — "
                "ältere Historie fehlt (die API verrät es nicht sicher, erkennbar "
                "nur an der exakt-2000-Signatur). Der Einzel-Button im Monitor kann "
                "bis 20.000 laden.\n"
                "2. **Keine Einzahlungs-/Balance-Zeilen** (Vantage) → keine "
                "belegbare Kapitalbasis → Prozentwerte entfallen (siehe oben).\n"
                "3. **Keine offenen Positionen** im Export → offenes Floating fehlt "
                "der Kurve; der echte Max-Drawdown kommt nur aus der Equity-Studie "
                "(Kursrekonstruktion)."),
            (
                "Warum sind Trades unter 1 Minute „gefährlich“?",
                "Beim Kopieren solche Trades mit eigener Latenz und Slippage "
                "möglicherweise **gar nicht erreichbar** — die eigene Kopie kann "
                "die Ergebnisse dann nicht reproduzieren. Die Haltezeit-Statistik "
                "markiert die Buckets „0 Sek“ und „<1 Min“ deshalb ROT und zeigt "
                "Anzahl + Anteil: je höher bei einem Scalper, desto kritischer. "
                "Zu finden im Detail der Alle-Signale-Seite unter „📋 Tradeliste + "
                "Haltezeit-Statistik“."),
        ],
    },
    {
        "titel": "Workflow & Ampel",
        "icon": "🚦",
        "fragen": [
            (
                "Wie entsteht die Ampel? Welche Regeln gelten?",
                "Grundprinzip: **Risiko VOR Ertrag.** Die harten Regeln:\n\n"
                "- **Max. 30 % Drawdown** — als konservatives MAXIMUM aus FÜNF "
                "Messungen (Plattform-By-Equity, By-Balance, Monitor-Nachmessung, "
                "gemessener Equity-DD aus Kursen, Peak-Exposure-Äquivalent). Ein "
                "guter Ertrag hebt eine verletzte Schranke NIE auf.\n"
                "- **Ertrag** über der Monatsschwelle (> 5 %/Monat), eigene "
                "geometrische Rendite statt Plattform-Selbstauskunft.\n"
                "- **TrueRetDD ≥ 3,0** (Jahres-Calmar) als Grün-Gate — nur mit "
                "belastbarer Kursmessung.\n"
                "- **Stop-Loss:** „kein Nachweis“ ist NEUTRAL (die meisten Broker "
                "übertragen keinen SL). Nur ein BEWIESENER Stop entlastet; "
                "abwerten darf allein die KI-Tiefenanalyse mit Begründung.\n\n"
                "Der Code rechnet alle Zahlen; das LLM bekommt fertige Befunde als "
                "JSON und darf nicht selbst rechnen."),
            (
                "Was sind Fix-IDs (📌) und wann nutze ich sie?",
                "Fix-IDs sind die „**Immer scannen**“-Liste: Diese Signal-ID läuft "
                "in JEDEN Scan-Lauf, **umgeht alle Vorfilter** (Mindestalter, "
                "Mindestabonnenten) und belegt keinen Quellen-Slot. Sinnvoll für "
                "einzelne junge Signale, die man trotzdem forensisch bewertet "
                "haben will — z. B. ein spezifisches Signal, das man selbst kopiert. "
                "Setzen über das Fix-Häkchen in der Detailansicht oder die "
                "Verwaltung auf der Ergebnisseite. Wichtig: Ein Fix ist eine "
                "Scan-Zusage, KEIN Vorzugsurteil — bewertet wird ganz normal."),
            (
                "Warum sagt die Alle-Signale-Seite, sie „bewertet nichts“?",
                "Sie ist die **unabhängige Vorstufe**: reine Statistik aus dem "
                "Trade-Cache (Monatsbalken, Kurve, Haltezeiten, Drawdowns) — ohne "
                "KI, ohne Ampel-Neuberechnung, ohne Urteil. Bewusst so gebaut: "
                "Erst selbst ein Bild machen (z. B. mit der Equity-Studie), DANN "
                "entscheidet der Workflow mit seinen Regeln. Ampel und Urteil "
                "bleiben allein beim Workflow-Scan."),
        ],
    },
    {
        "titel": "System & Datenlage",
        "icon": "🗂️",
        "fragen": [
            (
                "Wo werden die PDF-Berichte abgelegt?",
                "Konvention: **jedes Projekt schreibt in sein eigenes "
                "`data/reports/`**. Konkret im Workspace:\n\n"
                "- Monitor-Clients: `vantage/data/reports/`, "
                "`PelicanTrading/data/reports/`, `roboforex/data/reports/`, "
                "`zulumonitor/data/reports/` (je `bericht_<id>_<uuid>.pdf)\n"
                "- Scanner: `SignalKiScanner/data/reports/signale/<id>/` (je "
                "Report-Lauf ein Unterordner), `.../reports/portfolio/` "
                "(Portfolio-Berichte) und `doc/reports/` (Format-Referenzen)\n\n"
                "Insgesamt sind das über 1.400 PDFs — deshalb der Ordner statt "
                "Einzelablage."),
            (
                "Welche KI wird genutzt — und was darf sie?",
                "GLM über die Z.ai-API (OpenAI-kompatibel), zweistufig: eine "
                "**Flash-Klasse** für Massen-Profile beim Scan und das stärkere "
                "**GLM-5.3** für Gesamtbericht und Tiefenanalyse. Feste Regel: "
                "**Der Code rechnet ALLE Zahlen** — das LLM bekommt fertige Befunde "
                "als JSON und formuliert/liefert nur die Interpretation. Es rechnet "
                "nie selbst (Halluzinationsrisiko bei Arithmetik) und kann Ampel/"
                "Score nie verbessern — nur begründet abwerten. Die Agenten-Rollen "
                "(Dirigent, Beobachter, …) nutzen ebenfalls GLM-5.3."),
            (
                "Die Equity-Studie startet nicht — was braucht sie?",
                "Die Studie misst den echten Max-Drawdown aus **H1-Kursen** und "
                "braucht dafür das MT5-Referenzterminal — läuft gerade ein Scan, "
                "wartet sie (das Terminal wird exklusiv genutzt). Weitere "
                "ehrliche Grenzen: aktuell offene Positionen sind im Export nicht "
                "enthalten; Symbole ohne Kurse am Terminal werden NAMENTLICH "
                "gemeldet und erzeugen Messlücken; die GMT-Zeitbasis wird je Symbol "
                "aus Open/Close-Treffern abgeleitet (offengelegt in der Tabelle). "
                "Ergebnisse werden je (Signal, Trade-Stand) in der Sitzung gecacht "
                "— der zweite Klick ist sofort."),
        ],
    },
]


def alle_fragen() -> list[tuple[str, str]]:
    """Flache Liste (frage, antwort) über alle Kategorien — für Suche/Tests."""
    out: list[tuple[str, str]] = []
    for kategorie in FAQ_KATEGORIEN:
        out.extend(kategorie["fragen"])
    return out
