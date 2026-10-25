# Read-only process metadata; command lines remain in RAM and are never emitted.
$quellenOut = Split-Path -Parent $MyInvocation.MyCommand.Path
$quellenWorkspace = 'D:\AntiGravitySoftware\GitWorkspace\SIGNALDOWNLOADER'
$quellenMap = @{8089='MqlDownloader';8090='PelicanTrading';8091='roboforex';8092='vantage';8093='zulumonitor'}
$quellenListeners = Get-NetTCPConnection -State Listen | Where-Object { $quellenMap.ContainsKey([int]$_.LocalPort) }
$quellenRows = foreach ($quellenPort in 8089..8093) {
    $quellenListener = $quellenListeners | Where-Object { $_.LocalPort -eq $quellenPort } | Select-Object -First 1
    if ($null -eq $quellenListener) { [pscustomobject]@{port=$quellenPort;listening=$false};continue }
    $quellenProc = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $quellenListener.OwningProcess)
    $quellenArgs = [string]$quellenProc.CommandLine
    $quellenMain = [regex]::Match($quellenArgs,'(?:main\.MqlDownloaderApp|de\.(?:pelicanmonitor|robomonitor|vantagemonitor|zulumonitor)\.[A-Za-z]+App)').Value
    $quellenProject = $quellenMap[$quellenPort]
    $quellenRoot = Join-Path $quellenWorkspace $quellenProject
    $quellenFiles = if ($quellenProject -eq 'MqlDownloader') {
        @('src/rest/RestApiServer.java','src/gui/ClientUpdateRunner.java','src/gui/MqlDownloaderGui.java','target/classes/rest/RestApiServer.class','target/classes/gui/ClientUpdateRunner.class')
    } elseif ($quellenProject -eq 'vantage') {
        @('src/main/java/de/vantagemonitor/store/HistoryFiles.java','src/main/java/de/vantagemonitor/store/TradeStore.java','src/main/java/de/vantagemonitor/VantageMonitorApp.java','target/classes/de/vantagemonitor/VantageMonitorApp.class','target/classes/de/vantagemonitor/store/HistoryFiles.class')
    } else {
        $quellenPackage = @{PelicanTrading='pelicanmonitor';roboforex='robomonitor';zulumonitor='zulumonitor'}[$quellenProject]
        @("src/main/java/de/$quellenPackage/rest/RestApiServer.java","target/classes/de/$quellenPackage/rest/RestApiServer.class")
    }
    $quellenFileRows = foreach ($quellenRelative in $quellenFiles) {
        $quellenFile = Join-Path $quellenRoot $quellenRelative
        if (Test-Path -LiteralPath $quellenFile -PathType Leaf) {
            $quellenItem = Get-Item -LiteralPath $quellenFile
            [pscustomobject]@{relative=$quellenRelative;modifiedUtc=$quellenItem.LastWriteTimeUtc.ToString('o');modifiedAfterJvmStart=($quellenItem.LastWriteTimeUtc -gt $quellenProc.CreationDate.ToUniversalTime());sha256=(Get-FileHash -LiteralPath $quellenFile -Algorithm SHA256).Hash.ToLowerInvariant()}
        }
    }
    [pscustomobject]@{port=$quellenPort;project=$quellenProject;listening=$true;pid=$quellenProc.ProcessId;createdUtc=$quellenProc.CreationDate.ToUniversalTime().ToString('o');mainClass=$quellenMain;usesMavenExec=($quellenArgs -match 'org\.codehaus\.plexus\.classworlds');projectTargetClassesMentioned=$quellenArgs.Contains((Join-Path $quellenRoot 'target\classes'));files=$quellenFileRows}
}
$quellenResult = [pscustomobject]@{atUtc=[DateTime]::UtcNow.ToString('o');scope='Port owners and sanitized process metadata; current disk hashes do not hash already loaded JVM bytecode';productiveProcessesChanged=$false;sources=$quellenRows}
$quellenResult | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath (Join-Path $quellenOut 'quellen_process.json') -Encoding utf8
$quellenRows | Select-Object port,project,pid,createdUtc,mainClass | ConvertTo-Json
