$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$mqlRepo = [IO.Path]::GetFullPath((Join-Path $taskRoot '../MqlDownloader'))
$privateRoot = Join-Path $taskRoot 'data/runs/liveabschluss_20261019/mql'
$build = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'mql_metrics_rename_build_20261019.json') -Raw | ConvertFrom-Json
if ($build.tests.tests -ne 166 -or $build.tests.failures -or $build.tests.errors -or $build.tests.skipped -or $build.new_regression_failure_count -ne 3) { throw 'Isolated regression/full-suite proof missing' }
$stage = Join-Path $taskRoot '.tmp/source_maintenance/mql_metrics_stage_20261019/target/MqlDownloader-0.0.35-SNAPSHOT-jar-with-dependencies.jar'
$mqlJar = Join-Path $mqlRepo 'target/MqlDownloader-0.0.35-SNAPSHOT-jar-with-dependencies.jar'
$expectedPid = 52344
$previousSha = '59b6a9996628c040bfdcb36042eeecf1e68c52437ef1a3003a4f5fc138db37a7'
if ((Get-FileHash -LiteralPath $stage -Algorithm SHA256).Hash.ToLowerInvariant() -ne $build.jar_sha256) { throw 'Staged package hash mismatch' }
if ((Get-FileHash -LiteralPath $mqlJar -Algorithm SHA256).Hash.ToLowerInvariant() -ne $previousSha) { throw 'Active package changed' }
$processInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$expectedPid"
if (-not $processInfo -or -not $processInfo.CommandLine.Contains($mqlJar)) { throw 'MQL process identity changed' }
$listeners = @(Get-NetTCPConnection -LocalPort 8089 -State Listen)
if (-not $listeners.Count -or @($listeners | Where-Object { $_.OwningProcess -ne $expectedPid }).Count) { throw 'Unexpected API process' }
$api = Invoke-RestMethod -Uri 'http://127.0.0.1:8089/api/v1/update/status' -TimeoutSec 10
if ($api.state -ne 'idle') { throw 'Source job is active; no close requested' }
$javaRoot = 'C:/Program Files/Eclipse Adoptium/jdk-25.0.4.101-hotspot/bin'
$threads = (& (Join-Path $javaRoot 'jcmd.exe') $expectedPid Thread.print 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0 -or $threads -match 'downloader\.SignalDownloader|gui\.ClientUpdateRunner|gui\.ConversionManager') { throw 'Source writer absence not proven' }
$backup = Join-Path $privateRoot ('metrics_activation_backup_' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))
New-Item -ItemType Directory -Path $backup | Out-Null
$threads | Set-Content -LiteralPath (Join-Path $backup 'idle_threads_before_close.txt') -Encoding utf8
if ((Invoke-RestMethod -Uri 'http://127.0.0.1:8089/api/v1/update/status' -TimeoutSec 10).state -ne 'idle') { throw 'Source job changed; no close requested' }
$oldProcess = Get-Process -Id $expectedPid
if (-not $oldProcess.CloseMainWindow()) { throw 'Normal window close unavailable; no force-stop permitted' }
if (-not $oldProcess.WaitForExit(20000)) { throw 'Normal process exit unconfirmed; no replacement' }
if (Get-NetTCPConnection -LocalPort 8089 -State Listen -ErrorAction SilentlyContinue) { throw 'MQL port remains in use' }
$active = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('java.exe','javaw.exe') -and $_.CommandLine -match 'MqlDownloader|MqlAnalyzer' })
if ($active.Count) { throw 'Another MQL JVM exists; no replacement' }
# Complete immutable source data already has a hash-verified offline backup.
# Preserve current live DB/config files again after normal source shutdown.
$copied = @()
foreach ($folder in @('config','database')) {
    $destination = Join-Path $backup $folder
    New-Item -ItemType Directory -Path $destination | Out-Null
    Get-ChildItem -LiteralPath (Join-Path 'C:/Forex/MqlAnalyzer' $folder) -File | ForEach-Object {
        $target = Join-Path $destination $_.Name
        Copy-Item -LiteralPath $_.FullName -Destination $target
        $sourceSha = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sourceSha) { throw 'Offline live file backup mismatch' }
        $copied += [ordered]@{path=($folder + '/' + $_.Name);sha256=$sourceSha}
    }
}
Copy-Item -LiteralPath $mqlJar -Destination (Join-Path $backup 'previous.jar')
Copy-Item -LiteralPath (Join-Path $mqlRepo 'config/update_state.json') -Destination (Join-Path $backup 'update_state.json')
$copied | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $backup 'live_file_manifest.json') -Encoding utf8
Copy-Item -LiteralPath $stage -Destination $mqlJar
if ((Get-FileHash -LiteralPath $mqlJar -Algorithm SHA256).Hash.ToLowerInvariant() -ne $build.jar_sha256) { throw 'Installed package hash mismatch' }
$newProcess = Start-Process -FilePath (Join-Path $javaRoot 'java.exe') -ArgumentList @('-Dlog4j.configurationFile=file:///C:/Forex/MqlAnalyzer/config/log4j2.xml','-jar',$mqlJar) -WorkingDirectory $mqlRepo -WindowStyle Hidden -RedirectStandardOutput (Join-Path $privateRoot 'metrics_runtime.stdout.log') -RedirectStandardError (Join-Path $privateRoot 'metrics_runtime.stderr.log') -PassThru
$receipt = [ordered]@{
    utc=[DateTime]::UtcNow.ToString('o');source='mql5';source_uid='0a8faef1-a341-4899-a199-a87166b69079'
    old_pid=$expectedPid;new_pid=$newProcess.Id;normal_window_close=$true;idle_job_before_close=$true
    writer_stacks_absent=$true;port_end_confirmed=$true;offline_live_db_config_files_hash_verified=$copied.Count
    prior_complete_offline_backup_retained=$true;previous_jar_sha256=$previousSha;installed_jar_sha256=$build.jar_sha256
    active_jar_or_classes_overwritten=$false;source_update_post_sent=$false;scanner_db_or_settings_modified=$false
    normal_application_start=$true;source_data_files_rewritten=$false
}
$receipt | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $privateRoot 'metrics_activation.json') -Encoding utf8
$receipt | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'mql_metrics_rename_activation_20261019.json') -Encoding utf8
$receipt | ConvertTo-Json -Depth 5
