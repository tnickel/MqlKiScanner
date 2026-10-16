$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$reviewJava = 'C:\Program Files\Eclipse Adoptium\jdk-25.0.4.101-hotspot\bin\java.exe'
$reviewJavac = 'C:\Program Files\Eclipse Adoptium\jdk-25.0.4.101-hotspot\bin\javac.exe'

foreach ($reviewRepo in @('MqlDownloader', 'roboforex')) {
    $reviewXmlName = if ($reviewRepo -eq 'MqlDownloader') { 'TEST-rest.RestApiServerTest.xml' } else { 'TEST-de.robomonitor.RestApiServerTest.xml' }
    [xml]$reviewXml = Get-Content -LiteralPath (Join-Path $reviewRepo ('target/surefire-reports/' + $reviewXmlName))
    $reviewClasspath = ($reviewXml.testsuite.properties.property | Where-Object name -eq 'java.class.path').value
    $reviewOutput = if ($reviewRepo -eq 'MqlDownloader') { 'probe_classes_mql' } else { 'probe_classes_robo' }
    New-Item -ItemType Directory -Path $reviewOutput -Force | Out-Null
    if ($reviewRepo -eq 'MqlDownloader') {
        & $reviewJavac -cp $reviewClasspath -d $reviewOutput ReviewMqlProbe.java
        if ($LASTEXITCODE -ne 0) { throw 'MQL probe compile failed' }
        & $reviewJava -cp ($reviewOutput + ';' + $reviewClasspath) rest.ReviewMqlProbe (Join-Path $PSScriptRoot 'mql_probe_data') *> mql_probe.log
    } else {
        & $reviewJavac -cp $reviewClasspath -d $reviewOutput ReviewRoboProbe.java ReviewRoboWriterProbe.java
        if ($LASTEXITCODE -ne 0) { throw 'Robo probes compile failed' }
        & $reviewJava -cp ($reviewOutput + ';' + $reviewClasspath) de.robomonitor.rest.ReviewRoboProbe (Join-Path $PSScriptRoot 'robo_probe_data') *> robo_probe.log
        if ($LASTEXITCODE -ne 0) { throw 'Robo probe failed' }
        & $reviewJava -cp ($reviewOutput + ';' + $reviewClasspath) ReviewRoboWriterProbe (Join-Path $PSScriptRoot 'robo_parallel_data') *> robo_writer_probe.log
    }
    if ($LASTEXITCODE -ne 0) { throw 'Probe failed' }
}
& 'C:\Users\tnickel\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\python.exe' check_scanner_csv.py
if ($LASTEXITCODE -ne 0) { throw 'CSV parser probe failed' }
