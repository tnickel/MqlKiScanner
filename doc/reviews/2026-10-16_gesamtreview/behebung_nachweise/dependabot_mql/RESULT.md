# MqlDownloader: acht Dependabotmeldungen gezielt behoben

**Nachtrag Root:** Als Commit `908c69088a1fc8c36f20c3bffec7b3f9338bb987`
gepusht. Anschließende GitHub-API-Abfrage am 16.10.2026: alle acht Alerts
`fixed`, kein offener Alert. Beleg: `alerts_after.json`. Die folgenden
Abschnitte bewahren den Test- und Übergabestand des Quellenagenten.

Stand 16.10.2026. Basis-HEAD:
`eedd328dafcc1ccd678ca63e4a3da8c0d98e2824`.
Im echten Checkout ist ausschließlich `pom.xml` geändert: vier Versionszeilen.
Keine Compatibility-Quellcodekorrektur war für Kompilierung/Tests erforderlich.
Keine GUI, kein Browser, keine Plattform, kein Login und kein LLM wurden gestartet.
Maven-Central-Downloads waren für diesen Auftrag ausdrücklich erlaubt.
Kein Commit oder Push durch den Quellenagenten.

## Meldungen und Auswahl der Fixversionen

`gh api repos/tnickel/MqlDownloader/dependabot/alerts?state=open` bestätigte die
acht unten aufgeführten Meldungen. Der unveränderte API-Beleg liegt in
`alerts_before.json`. Dies ist eine Prüfung veröffentlichter verwundbarer
Versionsbereiche, kein Nachweis, dass alle jeweiligen Angriffsvoraussetzungen
im MQL-Workflow tatsächlich vorhanden waren.

| Alert | Paket und Änderung | Advisory | Erstes gepatchtes Release |
|---:|---|---|---|
| 1 | WebDriverManager 5.6.3 → **6.1.0** | [GHSA-pwm3-776c-8q7q / CVE-2025-4641](https://github.com/advisories/GHSA-pwm3-776c-8q7q) | 6.1.0 |
| 8 | jsoup 1.15.3 → **1.23.2** | [GHSA-65r4-943x-97jj / CVE-2026-75140](https://github.com/advisories/GHSA-65r4-943x-97jj) | 1.23.2 |
| 6 | dasselbe jsoup-Update | [GHSA-pmhh-3w7g-xqp8 / CVE-2026-71497](https://github.com/jhy/jsoup/security/advisories/GHSA-pmhh-3w7g-xqp8) | 1.23.1 |
| 7 | Log4j API 2.23.1 → **2.25.5** | [GHSA-qv9r-c865-cp47 / CVE-2026-49844](https://github.com/advisories/GHSA-qv9r-c865-cp47) | 2.25.5 |
| 5 | Log4j Core 2.23.1 → **2.25.5** | [GHSA-6hg6-v5c8-fphq / CVE-2026-34477](https://github.com/advisories/GHSA-6hg6-v5c8-fphq) | 2.25.4 |
| 4 | dasselbe Core-Update | [GHSA-445c-vh5m-36rj / CVE-2026-34478](https://github.com/advisories/GHSA-445c-vh5m-36rj) | 2.25.4 |
| 3 | dasselbe Core-Update | [GHSA-3pxv-7cmr-fjr4 / CVE-2026-34480](https://github.com/advisories/GHSA-3pxv-7cmr-fjr4) | 2.25.4 |
| 2 | dasselbe Core-Update | [GHSA-vc5p-v9hr-52mj / CVE-2025-68161](https://github.com/advisories/GHSA-vc5p-v9hr-52mj) | 2.25.3 |

API und Core bleiben gemeinsam auf 2.25.5. Das ist die kleinste gemeinsame
Releaseversion für diese fünf gemeldeten Log4j-Lücken. jsoup 1.23.2 deckt beide
gemeldeten jsoup-Lücken ab. Es wurden keine anderen direkten Abhängigkeiten oder
Buildplugins pauschal aktualisiert.

Zusätzliche Primärbelege:

- WebDriverManager: [Upstream-XXE-Korrektur PR 1458](https://github.com/bonigarcia/webdrivermanager/pull/1458).
- jsoup: [Release 1.23.2](https://jsoup.org/news/release-1.23.2),
  [Namespace-Speicherkorrektur PR 2556](https://github.com/jhy/jsoup/pull/2556),
  [Cleaner-Advisory des Maintainers](https://github.com/jhy/jsoup/security/advisories/GHSA-pmhh-3w7g-xqp8).
- Log4j: [Apache-Sicherheitsmeldungen](https://logging.apache.org/security.html),
  insbesondere die Abschnitte zu den fünf CVEs aus der Tabelle.

Die Schließung der GitHubmeldungen ist erst nach Root-Commit/Push und erneuter
Dependency-Graph-Auswertung von GitHub feststellbar. Der lokale Versionsfix und
Paketinhalt sind bereits geprüft; ein Nullbestand zukünftiger oder transitiver
Sicherheitsmeldungen wird damit nicht behauptet.

## Java-Mindestversion und Kompatibilität

- WebDriverManager 6.1.0 definiert Java 8 für Produktionscode, Java 11 für seine
  Tests: [getaggte Release-POM](https://github.com/bonigarcia/webdrivermanager/blob/webdrivermanager-6.1.0/pom.xml).
- jsoup 1.23.2 unterstützt Java 8+: [offizielle Download-/Runtimeangaben](https://jsoup.org/download).
- Log4j 2 benötigt Java 8+: [offizielle Installationsanforderungen](https://logging.apache.org/log4j/2.x/manual/installation.html#requirements).
- Das vorhandene Selenium 4.26.0 benötigt bereits Java 11:
  [Selenium zur Anhebung der Mindestversion](https://www.selenium.dev/blog/2023/java-8-support/).

Die vorhandenen README-Angaben Java 11+ sind deshalb weiterhin zutreffend;
keine README-Änderung nötig. Das unveränderte Maven-source/target 1.8 ist weiterhin
kein Nachweis einer Java-8-Laufzeitfähigkeit, wie die README ausdrücklich erklärt.
Der Bytecodeaudit des fertigen Distributions-JARs findet maximal Major 55
(Java 11) in den Basis-Runtimeklassen. Multi-Release-Alternativen wurden dabei
ausgenommen. Das ist eine notwendige Kompatibilitätsprüfung, kein vollständiger
Lauf auf Java 11. Tatsächlich getestet wurde Temurin **25.0.4.1+1-LTS**.

## Isolierter Build und Nachweise

Auditverzeichnis:
`D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/waste/dependabot_mql_2026-10-16/`.

Finaler Snapshot: `MqlDownloader_final/`.
Erzeugung per vorhandenem `audit/snapshot.py`: Archiv des Basis-HEADs plus genau
eine aktuelle Overlaydatei `pom.xml`. Der Helper liegt unter
`waste/gesamt_review_fixes_2026-10-16/audit/snapshot.py`.
Keine privaten Daten-/Cacheverzeichnisse wurden übernommen.

- **114 Tests, 0 Fehler, 0 Fehlschläge, 0 Skips.**
- **mvn -B package erfolgreich**, einschließlich Assembly-Distributions-JAR.
- Offline `mvn -o -B dependency:tree` erfolgreich; direkte aufgelöste Versionen
  stimmen mit den vier Zielversionen überein.
- `git diff --check` ohne Fehler; Checkout enthält nur `M pom.xml`.
- Nach Abschluss stimmte die Checkout-POM per SHA256 mit dem getesteten Overlay
  überein. `artifact_audit.json` bestätigt dieselben vier Versionen innerhalb der
  `META-INF/maven/*/pom.properties` des fertigen Distributions-JARs.

Dateien:

| Datei | Inhalt |
|---|---|
| `MqlDownloader_final.manifest.json` | Basis-HEAD und SHA256 des aktuellen POM-Overlays |
| `mql_security_package.log` | kompletter Download-, Compile-, 114-Test- und Package-Lauf |
| `mql_security_dependency_tree.log` | offline aufgelöster Abhängigkeitsbaum |
| `artifact_audit.json` | Versionsmetadaten, Klassenversionsübersicht und SHA256 |
| `audit_artifacts.py` | rein lesender, reproduzierbarer Artefaktcheck |
| `alerts_before.json` | acht ursprüngliche Dependabotmeldungen mit Referenzen |

POM-SHA256:
`dda0cd9588187ae4d5f768d0c38ee2a8fbf10a4221a6e8f8c6b07236bb268782`.

Getestetes Distributions-JAR-SHA256:
`52bc25182d6d89895b451368d65d67c322aa374f9a26172746d131fb32533884`.

Befehle im finalen Snapshot:

```powershell
$env:JAVA_HOME='C:\Program Files\Eclipse Adoptium\jdk-25.0.4.101-hotspot'
$env:PATH="$env:JAVA_HOME\bin;$env:PATH"
& 'D:\DevelopmentTools\apache-maven-3.9.6\bin\mvn.cmd' -B package
& 'D:\DevelopmentTools\apache-maven-3.9.6\bin\mvn.cmd' -o -B dependency:tree
```

Browser-/Treiberdownload und tatsächliche MQL-Webseitenkompatibilität wurden
bewusst nicht live ausgeführt. Der Nachweis umfasst Projektkompilierung,
vorhandene vollständige lokale Tests, Dependency-Auflösung und Paketinhalt.
